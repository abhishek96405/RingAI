"""
Test data factories for Duuutah AI.

Each factory returns a plain dict that mirrors the shape of the corresponding
Mongo document. Override via kwargs:

    restaurant = make_restaurant(id="custom-id", name="Custom Diner")

Factories never write to a database. Tests insert returned dicts explicitly
to keep test setup visible at the call site.
"""
from .restaurant import make_restaurant
from .salon import make_salon
from .menu_item import make_menu_item
from .modifier_group import make_modifier_group
from .service_item import make_service_item
from .appointment import make_appointment
from .blocked_slot import make_blocked_slot
from .reservation import make_reservation
from .call_record import make_call_record
from .customer_profile import make_customer_profile
from .user import make_user
from .membership import make_membership
from .transcript import make_transcript

__all__ = [
    "make_restaurant",
    "make_salon",
    "make_menu_item",
    "make_modifier_group",
    "make_service_item",
    "make_appointment",
    "make_blocked_slot",
    "make_reservation",
    "make_call_record",
    "make_customer_profile",
    "make_user",
    "make_membership",
    "make_transcript",
]
