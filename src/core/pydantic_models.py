from datetime import date, datetime
from enum import Enum
import json
from typing import Optional, Type, TypeVar

from pydantic import Field, root_validator, validator
from pydantic.main import BaseModel as PydanticBaseModel

_Model = TypeVar('_Model', bound='BaseModel')


class BaseModel(PydanticBaseModel):
    @classmethod
    def parse_obj(cls: Type[_Model], obj: dict) -> Optional[_Model]:
        obj = obj.copy()
        if not isinstance(obj, dict):
            return super().parse_obj(obj)

        child_values = {}

        has_data = False
        for member_name, field in cls.__fields__.items():
            if getattr(field.type_, 'parse_obj', None):
                child_values[member_name] = field.type_.parse_obj(obj)
            else:
                alias = field.alias or field.name
                has_data = has_data or obj.get(alias) is not None

        if not has_data and not child_values:
            return None

        obj.update(child_values)
        result = cls(**obj)

        return result


class Proxy(BaseModel):
    class Type(Enum):
        SOCKS5 = "socks5"
        HTTP = "http"
        HTTPS = "https"

    login: str = Field(alias="proxy_login")
    password: str = Field(alias="proxy_password")
    ip: str = Field(alias="proxy_ip")
    port: str = Field(alias="proxy_port")
    type: Type = Field(alias="proxy_type")
    mobile: bool = Field(alias="proxy_mobile")
    expiration_date: date = Field(alias="proxy_expiration_date")
    price: int = Field(alias="proxy_price")

    @validator("expiration_date", pre=True)
    def parse_expiration_date(cls, value):
        return datetime.strptime(value, "%d.%m.%Y").date()

    class Config:
        use_enum_values = True
        allow_population_by_field_name = True


class Cookie(BaseModel):
    name: str
    value: str
    domain: str
    path: str
    secure: bool
    expires: Optional[float]

    @root_validator(pre=True)
    @classmethod
    def validate(cls, field_values):
        expires = field_values.get("expiry") or field_values.get("expires") or field_values.get("expirationDate")
        return {
            **field_values,
            "expires": expires
        }


class Account(BaseModel):
    network: str
    login: Optional[str]
    password: Optional[str]
    price: str
    token: Optional[str]
    cookies: Optional[list]
    proxy: Optional[Proxy]

    @validator("cookies", pre=True)
    def parse_cookies(cls, value):
        return [Cookie.parse_obj(cookie).dict() for cookie in json.loads(value)]

    @root_validator
    @classmethod
    def validate(cls, field_values):
        assert any([
            all([field_values.get("login"), field_values.get("password")]),
            field_values.get("cookies"),
            field_values.get("token"),
        ]), "Должны присутствовать: login+password | cookies | token"

        return field_values
