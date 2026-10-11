import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

API_URL = "https://api.novaposhta.ua/v2.0/json/"

CITIES_LIMIT = 8
WAREHOUSES_LIMIT = 10


class NovaPoshtaError(Exception):
    """Сервис Новой почты недоступен или вернул ошибку."""


class NovaPoshtaTransportError(NovaPoshtaError):
    """Не удалось получить подтверждённый ответ от API Новой почты."""


class NovaPoshtaWaybillOutcomeUnknown(NovaPoshtaError):
    """Запрос накладной ушёл, но результат создания нельзя подтвердить."""


@dataclass(frozen=True, slots=True)
class City:
    ref: str 
    name: str


@dataclass(frozen=True, slots=True)
class Warehouse:
    ref: str
    description: str


@dataclass(frozen=True, slots=True)
class Sender:
    ref: str
    name: str
    city_name: str


@dataclass(frozen=True, slots=True)
class SenderContact:
    ref: str
    name: str
    phone: str


@dataclass(frozen=True, slots=True)
class Waybill:
    ref: str
    number: str


class NovaPoshtaClient:
    def __init__(self, api_key: str, timeout: float = 10.0) -> None:
        self._api_key = api_key
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

    async def _call(
        self, model: str, method: str, properties: dict[str, Any]
    ) -> list[dict[str, Any]]:
        payload = {
            "apiKey": self._api_key,
            "modelName": model,
            "calledMethod": method,
            "methodProperties": properties,
        }
        try:
            async with self._get_session().post(API_URL, json=payload) as response:
                response.raise_for_status()
                body = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise NovaPoshtaTransportError(
                f"{model}.{method}: сервис недоступен ({exc!r})"
            ) from exc

        if not isinstance(body, dict) or not body.get("success"):
            errors = body.get("errors") if isinstance(body, dict) else None
            raise NovaPoshtaError(f"{model}.{method}: ошибка API: {errors or 'неизвестная'}")

        return body.get("data") or []

    async def search_cities(self, query: str) -> list[City]:
        data = await self._call(
            "Address",
            "searchSettlements",
            {"CityName": query, "Limit": str(CITIES_LIMIT), "Page": "1"},
        )
        addresses = data[0].get("Addresses", []) if data else []

        cities: list[City] = []
        for item in addresses:
            ref = item.get("DeliveryCity")
            if not ref or item.get("Warehouses") in (0, "0"):
                continue
            name = item.get("Present") or item.get("MainDescription")
            if name:
                cities.append(City(ref=ref, name=name))
        return cities

    async def search_warehouses(self, city_ref: str, query: str = "") -> list[Warehouse]:
        properties: dict[str, Any] = {
            "CityRef": city_ref,
            "Limit": str(WAREHOUSES_LIMIT),
            "Page": "1",
            "Language": "UA",
        }
        if query:
            properties["FindByString"] = query

        data = await self._call("Address", "getWarehouses", properties)
        return [
            Warehouse(ref=item["Ref"], description=item["Description"])
            for item in data
            if item.get("Ref") and item.get("Description")
        ]

    async def get_senders(self) -> list[Sender]:
        data = await self._call(
            "Counterparty",
            "getCounterparties",
            {"CounterpartyProperty": "Sender", "Page": "1"},
        )
        senders: list[Sender] = []
        for item in data:
            ref = item.get("Ref")
            city_name = (
                item.get("CityDescription")
                or item.get("CityDescriptionRu")
                or item.get("CityName")
                or ""
            )
            if not ref:
                continue
            senders.append(
                Sender(
                    ref=ref,
                    name=item.get("Description") or item.get("DescriptionRu") or "Отправитель",
                    city_name=city_name,
                )
            )
        return senders

    async def get_sender_contacts(self, sender_ref: str) -> list[SenderContact]:
        data = await self._call(
            "Counterparty",
            "getCounterpartyContactPersons",
            {"Ref": sender_ref},
        )
        return [
            SenderContact(
                ref=item["Ref"],
                name=item.get("Description") or "Контакт отправителя",
                phone=item.get("Phones") or item.get("Phone") or "",
            )
            for item in data
            if item.get("Ref") and (item.get("Phones") or item.get("Phone"))
        ]

    async def create_waybill(
        self,
        *,
        sender_ref: str,
        sender_city_ref: str,
        sender_warehouse_ref: str,
        sender_contact_ref: str,
        sender_phone: str,
        city_ref: str,
        warehouse_ref: str,
        full_name: str,
        phone: str,
        product_name: str,
        product_size: str,
        price: float,
    ) -> Waybill:
        name_parts = full_name.split()
        if len(name_parts) < 2:
            raise NovaPoshtaError("Для создания накладной не хватает ФИО получателя")
        for value, label in (
            (sender_ref, "отправителя"),
            (sender_city_ref, "города отправителя"),
            (sender_warehouse_ref, "отделения отправителя"),
            (sender_contact_ref, "контактного лица отправителя"),
            (city_ref, "города получателя"),
            (warehouse_ref, "отделения получателя"),
        ):
            self._required_ref(value, label)

        recipient = await self._call(
            "Counterparty",
            "save",
            {
                "FirstName": name_parts[1],
                "MiddleName": " ".join(name_parts[2:]),
                "LastName": name_parts[0],
                "Phone": phone.removeprefix("+"),
                "CounterpartyType": "PrivatePerson",
                "CounterpartyProperty": "Recipient",
            },
        )
        recipient_ref = recipient[0].get("Ref") if recipient else None
        if not recipient_ref:
            raise NovaPoshtaError("Новая почта не вернула идентификатор получателя")

        contact = await self._call(
            "ContactPerson",
            "save",
            {
                "CounterpartyRef": recipient_ref,
                "FirstName": name_parts[1],
                "MiddleName": " ".join(name_parts[2:]),
                "LastName": name_parts[0],
                "Phone": phone.removeprefix("+"),
            },
        )
        contact_ref = contact[0].get("Ref") if contact else None
        if not contact_ref:
            raise NovaPoshtaError("Новая почта не вернула контакт получателя")

        amount = f"{price:.2f}"
        try:
            documents = await self._call(
                "InternetDocument",
                "save",
                {
                    "PayerType": "Recipient",
                    "PaymentMethod": "Cash",
                    "DateTime": date.today().strftime("%d.%m.%Y"),
                    "CargoType": "Parcel",
                    "Weight": "1",
                    "SeatsAmount": 1,
                    "Description": f"{product_name} ({product_size})"[:36],
                    "Cost": amount,
                    "ServiceType": "WarehouseWarehouse",
                    "CitySender": sender_city_ref,
                    "Sender": sender_ref,
                    "SenderAddress": sender_warehouse_ref,
                    "ContactSender": sender_contact_ref,
                    "SendersPhone": sender_phone,
                    "CityRecipient": city_ref,
                    "Recipient": recipient_ref,
                    "RecipientAddress": warehouse_ref,
                    "ContactRecipient": contact_ref,
                    "RecipientsPhone": phone,
                    "BackwardDeliveryData": [
                        {
                            "PayerType": "Recipient",
                            "CargoType": "Money",
                            "RedeliveryString": amount,
                        }
                    ],
                },
            )
        except NovaPoshtaTransportError as exc:
            raise NovaPoshtaWaybillOutcomeUnknown(
                "Запрос создания накладной отправлен, но ответ не получен"
            ) from exc
        if not documents or not documents[0].get("IntDocNumber"):
            raise NovaPoshtaWaybillOutcomeUnknown(
                "Новая почта приняла запрос, но не вернула номер накладной"
            )
        return Waybill(
            ref=documents[0].get("Ref", ""),
            number=documents[0]["IntDocNumber"],
        )

    @staticmethod
    def _required_ref(value: str, label: str) -> str:
        if not value:
            raise NovaPoshtaError(f"Не настроен идентификатор {label}")
        return value
