# --- Owner: (assign, see docs/TEAM_SPLIT.md) | move-in charge check, the tool the model calls (capability 2) ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
"""Check move-in charges against M.G.L. c. 186 §15B(1)(b).

At or before the start of a tenancy a Massachusetts landlord may collect only:
  - first month's rent,
  - last month's rent (at the same rate as the first month),
  - a security deposit no larger than one month's rent,
  - the purchase and installation cost of a new lock and key.
Anything else (pet fees, application fees, move-in or cleaning fees, extra deposits) is not allowed.

This is arithmetic and a fixed list, so it is code, not a model judgment. The model's job is only to
read the lease, find the amounts, and decide to call this function with them.
"""
from __future__ import annotations

from typing import Any

from google.genai import types

CITE_15B_1B = "M.G.L. c. 186 §15B(1)(b)"
CITE_BROKER = "Massachusetts broker-fee law, effective Aug. 1, 2025 (verify the citation)"

OK, CHECK, NOT_ALLOWED = "ok", "check", "not_allowed"


def check_move_in_charges(
    monthly_rent: float,
    first_month_rent: float = 0.0,
    last_month_rent: float = 0.0,
    security_deposit: float = 0.0,
    lock_and_key_fee: float = 0.0,
    other_fees: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return one verdict per charge, plus totals. All amounts are in US dollars."""
    rent = float(monthly_rent or 0)
    if rent <= 0:
        return {"error": "monthly_rent must be a positive number of dollars."}

    items: list[dict[str, Any]] = []

    def add(name: str, amount: float, status: str, reason: str, citation: str = CITE_15B_1B) -> None:
        items.append({"charge": name, "amount": round(float(amount), 2), "status": status,
                      "reason": reason, "citation": citation})

    if first_month_rent:
        if first_month_rent > rent + 0.01:
            add("First month's rent", first_month_rent, NOT_ALLOWED,
                f"More than one month's rent (${rent:,.2f}).")
        else:
            add("First month's rent", first_month_rent, OK, "Allowed.")

    if last_month_rent:
        if last_month_rent > rent + 0.01:
            add("Last month's rent", last_month_rent, NOT_ALLOWED,
                f"Last month's rent must be at the same rate as the first month (${rent:,.2f}).")
        else:
            add("Last month's rent", last_month_rent, OK,
                "Allowed. The landlord must give a receipt and pay you interest on it every year.")

    # Pet deposits and similar are security deposits under the statute, so they count toward the cap.
    extra_deposits = 0.0
    fees = []
    for fee in other_fees or []:
        name = str(fee.get("name", "Other fee")).strip() or "Other fee"
        amount = float(fee.get("amount", 0) or 0)
        if amount <= 0:
            continue
        if "deposit" in name.lower():
            extra_deposits += amount
        fees.append((name, amount))

    total_deposit = float(security_deposit or 0) + extra_deposits
    if total_deposit:
        label = "Security deposit" + (" (including other deposits)" if extra_deposits else "")
        if total_deposit > rent + 0.01:
            add(label, total_deposit, NOT_ALLOWED,
                f"Deposits total ${total_deposit:,.2f}, more than one month's rent (${rent:,.2f}).")
        else:
            add(label, total_deposit, OK,
                "Allowed. It must be held in a separate Massachusetts bank account and earns interest.")

    if lock_and_key_fee:
        add("Lock and key", lock_and_key_fee, CHECK,
            "Allowed only if it is the actual cost of buying and installing a new lock and key.")

    for name, amount in fees:
        lower = name.lower()
        if "deposit" in lower:
            continue  # already counted in the deposit cap above
        if "broker" in lower or "finder" in lower or "agent" in lower:
            add(name, amount, CHECK,
                "Since Aug. 1, 2025 you pay a broker only if you hired the broker yourself. "
                "If the landlord hired them, the landlord pays.", CITE_BROKER)
        else:
            add(name, amount, NOT_ALLOWED,
                "Not one of the four charges a landlord may collect at move-in.")

    allowed_max = 3 * rent  # first + last + deposit, before lock cost
    total = sum(i["amount"] for i in items)
    return {
        "monthly_rent": rent,
        "items": items,
        "total_requested": round(total, 2),
        "maximum_allowed_excluding_lock": round(allowed_max, 2),
        "problems_found": sum(1 for i in items if i["status"] == NOT_ALLOWED),
        "needs_checking": sum(1 for i in items if i["status"] == CHECK),
    }


# The declaration the model sees. Its descriptions are what lead the model to call the tool.
CHECK_MOVE_IN_CHARGES_DECLARATION = types.FunctionDeclaration(
    name="check_move_in_charges",
    description=(
        "Checks the money a Massachusetts landlord asks for at or before move-in against the legal limits. "
        "Call it whenever the lease states any move-in amount: first or last month's rent, a security "
        "deposit, a lock fee, or any other fee or deposit due before or at the start of the tenancy."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "monthly_rent": types.Schema(type=types.Type.NUMBER, description="The regular monthly rent in dollars."),
            "first_month_rent": types.Schema(type=types.Type.NUMBER, description="First month's rent due at signing. 0 if not stated."),
            "last_month_rent": types.Schema(type=types.Type.NUMBER, description="Last month's rent collected in advance. 0 if not stated."),
            "security_deposit": types.Schema(type=types.Type.NUMBER, description="The security deposit. 0 if none."),
            "lock_and_key_fee": types.Schema(type=types.Type.NUMBER, description="Fee for a lock and key. 0 if none."),
            "other_fees": types.Schema(
                type=types.Type.ARRAY,
                description="Every other fee or deposit due at or before move-in (pet fee, application fee, broker fee, cleaning fee, pet deposit...).",
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "name": types.Schema(type=types.Type.STRING),
                        "amount": types.Schema(type=types.Type.NUMBER),
                    },
                    required=["name", "amount"],
                ),
            ),
        },
        required=["monthly_rent"],
    ),
)

TOOLS = {"check_move_in_charges": check_move_in_charges}
