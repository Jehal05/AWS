from renewflow.pricing import amounts_in, build_quote, inr


def test_inr_uses_indian_grouping():
    assert inr(950) == "₹950"
    assert inr(18400) == "₹18,400"
    assert inr(150000) == "₹1,50,000"
    assert inr(-3600) == "-₹3,600"


def test_quarterly_quote_adds_disclosed_loading():
    q = build_quote(18400, "quarterly")
    assert (q.installments, q.per_installment, q.total, q.surcharge) == (4, 4738, 18952, 552)


def test_monthly_and_annual_quotes():
    monthly = build_quote(18400, "monthly")
    assert (monthly.per_installment, monthly.total, monthly.surcharge) == (1625, 19500, 1100)
    annual = build_quote(18400, "annual")
    assert (annual.installments, annual.total, annual.surcharge) == (1, 18400, 0)


def test_amounts_in_finds_every_rupee_figure():
    assert amounts_in("Pay ₹18,400 or Rs. 4,738 or INR 99") == [18400, 4738, 99]
    assert amounts_in("no money here, just 12 apples") == []
