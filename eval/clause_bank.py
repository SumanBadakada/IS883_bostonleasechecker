# --- Owner: (assign, see docs/TEAM_SPLIT.md) | labelled clause bank for the synthetic test leases ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
"""Every clause the synthetic leases are built from, with its expected label written BEFORE any run.

Labels follow the labelling guide in eval/LABELING_GUIDE.md. `cite` lists the source chunk IDs
(sources/*.md) that support a possibly_unlawful label; a prediction citing any of them counts as a
correct citation. Two team members should review every label here and record disagreements.
"""

# (key, text, label, cite)
LAWFUL = [
    ("use", "USE OF PREMISES. The premises shall be used only as a private residence for the persons named in this lease.", "lawful", []),
    ("trash", "CLEANLINESS. Tenant shall keep the apartment clean and sanitary and shall put all trash and recycling in the containers provided.", "lawful", []),
    ("sublet", "ASSIGNMENT AND SUBLETTING. Tenant shall not assign this lease or sublet the apartment without Landlord's prior written consent.", "lawful", []),
    ("noise", "NOISE. Tenant shall not make or allow noise that disturbs other residents, especially between 10 p.m. and 7 a.m.", "lawful", []),
    ("smoking", "SMOKING. Smoking of any substance is not permitted anywhere in the apartment or the building.", "lawful", []),
    ("insurance", "RENTER'S INSURANCE. Tenant shall maintain renter's insurance covering Tenant's personal property throughout the tenancy.", "lawful", []),
    ("electric", "UTILITIES. Tenant shall pay for electricity, which is separately metered for the apartment and billed in Tenant's name. Landlord shall provide heat and hot water.", "lawful", []),
    ("entry_ok", "ACCESS. Landlord may enter the apartment at reasonable times, with 24 hours' notice except in an emergency, to inspect it, make repairs, or show it to prospective tenants or buyers.", "lawful", []),
    ("damage", "DAMAGE. Tenant shall pay the reasonable cost of repairing damage caused by Tenant or Tenant's guests, other than normal wear and tear.", "lawful", []),
    ("alter", "ALTERATIONS. Tenant shall not paint, install fixtures or make alterations to the apartment without Landlord's written consent.", "lawful", []),
    ("repairs_ok", "LANDLORD'S REPAIRS. Landlord shall keep the building and the apartment's heating, plumbing and electrical systems in good repair as required by the State Sanitary Code.", "lawful", []),
    ("contact", "NOTICES. Repair requests and notices to Landlord shall be sent to Beacon Property Management, 100 Main Street, Boston, MA 02108, telephone (617) 555-0100, which manages the building for the owner.", "lawful", []),
    ("return_ok", "RETURN OF DEPOSIT. Landlord shall return the security deposit, with interest, within thirty days after the tenancy ends, less only the deductions allowed by law, itemized as the law requires.", "lawful", []),
    ("occupancy", "OCCUPANCY. No more than two persons shall live in the apartment.", "lawful", []),
    ("pets_consent", "PETS. No pets are allowed in the apartment without Landlord's written consent.", "lawful", []),
    ("keys", "KEYS. At the end of the tenancy Tenant shall return all keys to Landlord.", "lawful", []),
    ("parking", "PARKING. One parking space is included with the apartment. Tenant shall not park in spaces assigned to other units.", "lawful", []),
    ("account_ok", "DEPOSIT ACCOUNT. The security deposit will be held in a separate interest-bearing account at a Massachusetts bank, and Tenant will receive a receipt naming the bank, its address and the account number within thirty days.", "lawful", []),
    ("condition_ok", "STATEMENT OF CONDITION. Landlord will give Tenant a written statement of the apartment's condition within ten days after the tenancy begins.", "lawful", []),
    ("lead_ok", "LEAD PAINT. The building was built before 1978. Before signing, Landlord gave Tenant the Tenant Lead Law Notification and the Tenant Certification form.", "lawful", []),
    ("laundry", "LAUNDRY. Coin-operated washers and dryers are available in the basement for the use of all tenants.", "lawful", []),
]

UNUSUAL = [
    ("carpet", "CARPETS. Tenant shall have all carpets professionally cleaned at the end of the tenancy and give Landlord the receipt.", "unusual", []),
    ("guests", "GUESTS. Tenant may not have overnight guests for more than three nights in any month without Landlord's written permission.", "unusual", []),
    ("lockout_fee", "LOCKOUTS. Tenant shall pay $75 each time Landlord or its agent is called to let Tenant into the apartment after business hours.", "unusual", []),
    ("nails", "WALLS. Tenant shall not hang pictures or use nails, screws or adhesive hooks on any wall.", "unusual", []),
    ("returned_check", "RETURNED PAYMENTS. A rent check returned unpaid by the bank will incur a $40 returned-check fee.", "unusual", []),
    ("moveout_notice", "NOTICE OF MOVE-OUT. Tenant must give Landlord 60 days' written notice before moving out at the end of the lease term.", "unusual", []),
    ("auto_renew", "RENEWAL. This lease renews automatically for another twelve months unless Tenant gives written notice at least 90 days before it ends.", "unusual", []),
    ("ac", "AIR CONDITIONING. Tenant shall not install a window air-conditioning unit.", "unusual", []),
]

UNLAWFUL = [
    ("late_fee", "LATE PAYMENT. If rent is not received by the 5th day of the month, Tenant shall pay a late charge of $50, plus $10 for each additional day.", "possibly_unlawful", ["c186-15B-1c"]),
    ("entry_any", "ACCESS. Landlord and Landlord's agents may enter the apartment at any time, with or without notice, for any purpose.", "possibly_unlawful", ["c186-15B-1a"]),
    ("cleaning_keep", "CLEANING. $300 of the security deposit is a non-refundable cleaning fee that Landlord will keep at the end of the tenancy regardless of the apartment's condition.", "possibly_unlawful", ["c186-15B-4", "c186-15B-8", "c186-15B-1b"]),
    ("no_interest", "INTEREST. Tenant agrees that no interest will be paid on the security deposit or on last month's rent.", "possibly_unlawful", ["c186-15B-3b", "c186-15B-2a", "c186-15B-8"]),
    ("liability", "LIABILITY. Landlord shall not be liable for any injury to Tenant or damage to Tenant's property, even if caused by Landlord's negligence.", "possibly_unlawful", ["ag-liability", "cmr-3.17-3a"]),
    ("all_repairs", "CONDITION AND REPAIRS. Tenant accepts the apartment as is and shall be responsible for all repairs, including the heating, plumbing and electrical systems.", "possibly_unlawful", ["ag-repairs", "cmr-3.17-1", "cmr-3.17-3a"]),
    ("lock_out", "NON-PAYMENT. If Tenant fails to pay rent, Landlord may change the locks and remove Tenant's belongings without going to court.", "possibly_unlawful", ["ag-eviction", "cmr-3.17-5"]),
    ("forfeit", "EARLY TERMINATION. If Tenant moves out before the end of the term for any reason, the entire security deposit is forfeited as liquidated damages.", "possibly_unlawful", ["c186-15B-4", "c186-15B-8"]),
    ("heat", "HEATING SEASON. Landlord is not required to provide heat before November 1 or after April 1.", "possibly_unlawful", ["ag-heat-utilities", "ag-repairs", "cmr-3.17-1"]),
    ("children", "CHILDREN. Tenant certifies that no child under six will live in the apartment, and agrees that this lease ends if one does.", "possibly_unlawful", ["ag-lead", "ag-discrimination"]),
    ("no_report", "COMPLAINTS. Tenant agrees not to report conditions in the apartment to the Boston Inspectional Services Department or any other agency.", "possibly_unlawful", ["cmr-3.17-5", "ag-retaliation", "cmr-3.17-3a"]),
    ("pests", "PEST CONTROL. Tenant shall pay for all extermination and pest control, whatever the cause of the infestation.", "possibly_unlawful", ["ag-repairs", "cmr-3.17-1", "cmr-3.17-3a"]),
    ("water", "WATER. Tenant shall pay a flat water and sewer charge of $60 per month in addition to rent.", "possibly_unlawful", ["ag-heat-utilities"]),
]

# Move-in payment clauses. Each lease gets exactly one. `charges` is the expected tool input and outcome.
# fmt(rent) -> (text, label, cite, expected)
def money_clauses(rent: int):
    r = f"${rent:,}"
    return {
        "m_ok": (
            f"PAYMENTS AT SIGNING. At signing Tenant shall pay first month's rent of {r}, last month's rent of {r}, and a security deposit of {r}.",
            "lawful", [], {"monthly_rent": rent, "security_deposit": rent, "problems_found": 0}),
        "m_deposit_high": (
            f"PAYMENTS AT SIGNING. At signing Tenant shall pay first month's rent of {r} and a security deposit of ${int(rent * 1.5):,}.",
            "possibly_unlawful", ["c186-15B-1b", "ag-move-in-costs"],
            {"monthly_rent": rent, "security_deposit": int(rent * 1.5), "problems_found": 1}),
        "m_pet_fee": (
            f"PAYMENTS AT SIGNING. At signing Tenant shall pay first month's rent of {r}, a security deposit of {r}, and a non-refundable pet fee of $300.",
            "possibly_unlawful", ["c186-15B-1b", "ag-move-in-costs"],
            {"monthly_rent": rent, "security_deposit": rent, "problems_found": 1}),
        "m_app_fee": (
            f"PAYMENTS AT SIGNING. Tenant shall pay an application fee of $50 and a move-in fee of $250, together with first month's rent of {r} and last month's rent of {r}.",
            "possibly_unlawful", ["c186-15B-1b", "ag-move-in-costs"],
            {"monthly_rent": rent, "security_deposit": 0, "problems_found": 2}),
        "m_pet_deposit": (
            f"PAYMENTS AT SIGNING. At signing Tenant shall pay first month's rent of {r}, a security deposit of {r}, and a refundable pet deposit of $500.",
            "possibly_unlawful", ["c186-15B-1b", "ag-move-in-costs"],
            {"monthly_rent": rent, "security_deposit": rent, "problems_found": 1}),
        "m_lock": (
            f"PAYMENTS AT SIGNING. At signing Tenant shall pay first month's rent of {r}, last month's rent of {r}, a security deposit of {r}, and $85 for the purchase and installation of a new lock and key.",
            "lawful", [], {"monthly_rent": rent, "security_deposit": rent, "problems_found": 0}),
        "m_broker": (
            f"PAYMENTS AT SIGNING. At signing Tenant shall pay first month's rent of {r}, a security deposit of {r}, and a broker fee of {r} to Back Bay Realty, the leasing agent Landlord hired to list the apartment.",
            "possibly_unlawful", ["ag-broker-fees"],
            {"monthly_rent": rent, "security_deposit": rent, "problems_found": 0}),
        "m_last_high": (
            f"PAYMENTS AT SIGNING. At signing Tenant shall pay first month's rent of {r} and last month's rent of ${rent + 200:,}, because rent may rise next year.",
            "possibly_unlawful", ["c186-15B-1b", "ag-move-in-costs"],
            {"monthly_rent": rent, "security_deposit": 0, "problems_found": 1}),
    }
