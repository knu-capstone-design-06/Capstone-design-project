from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, StrictInt


Temperature = Literal["iced", "hot"]
Category = Literal["coffee", "drink", "food"]


class Product(BaseModel):
    product_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: Category
    description: str
    unit_price: StrictInt = Field(ge=0)
    available: StrictBool
    temperatures: list[Temperature]


class ProductList(BaseModel):
    currency: Literal["KRW"] = "KRW"
    products: list[Product]


class CartItem(BaseModel):
    item_id: str
    product_id: str
    name: str
    temperature: Temperature | None
    quantity: StrictInt = Field(ge=1, le=20)
    unit_price: StrictInt = Field(ge=0)
    line_amount: StrictInt = Field(ge=0)


class Cart(BaseModel):
    session_id: str
    version: StrictInt = Field(ge=0)
    currency: Literal["KRW"] = "KRW"
    items: list[CartItem]
    total_quantity: StrictInt = Field(ge=0)
    total_amount: StrictInt = Field(ge=0)
    updated_at: AwareDatetime


class Order(BaseModel):
    order_id: str
    order_number: str
    session_id: str
    status: Literal["simulated"] = "simulated"
    currency: Literal["KRW"] = "KRW"
    items: list[CartItem] = Field(min_length=1)
    total_quantity: StrictInt = Field(ge=1)
    total_amount: StrictInt = Field(ge=0)
    created_at: AwareDatetime


class OrderApiError(BaseModel):
    code: str
    detail: str
    cart: Cart | None = None


class OrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: StrictInt = Field(ge=0)


class AddItemRequest(OrderRequest):
    product_id: str = Field(min_length=1)
    temperature: Temperature | None
    quantity: StrictInt = Field(ge=1, le=20)


class UpdateItemRequest(OrderRequest):
    quantity: StrictInt = Field(ge=1, le=20)
