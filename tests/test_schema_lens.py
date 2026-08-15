"""REQ-011 value_lens + management_tone validation tests."""
from earnings_digest import schema

TRANSCRIPT = (
    "[00:10] เรามีสัญญาก๊าซระยะยาวกับลูกค้าหลักครับ "
    "[00:40] ผู้บริหารบอกว่าจะซื้อหุ้นคืนถ้าราคาต่ำกว่ามูลค่า "
    "[01:00] มาร์จิ้นโรงกลั่นอยู่ที่ 5.2 ดอลลาร์ต่อบาร์เรล"
)


def _base(**over):
    d = {
        "summary": ["PTT quarterly update"],
        "claims": [],
        "value_lens": {
            "moat_durability": [
                {
                    "text": "Long-term gas contracts anchor the moat",
                    "type": "fact",
                    "speaker": "CFO",
                    "ts": "00:10",
                    "basis": "stated",
                    "quote": "สัญญาก๊าซระยะยาว",
                }
            ]
        },
        "management_tone": {
            "label": "bullish",
            "rationale": "Buyback talk plus confident guidance.",
            "quotes": ["จะซื้อหุ้นคืนถ้าราคาต่ำกว่ามูลค่า"],
        },
    }
    d.update(over)
    return d


def test_lens_and_tone_validate_and_anchor():
    norm, rep = schema.validate(_base(), TRANSCRIPT, 600)
    assert rep.ok, rep.errors
    lens = norm["value_lens"]["moat_durability"]
    assert lens[0]["verification"] == "quote_verified"
    assert norm["management_tone"]["label"] == "bullish"
    assert norm["management_tone"]["quotes"][0]["verification"] == "quote_verified"


def test_lens_fact_requires_quote():
    d = _base()
    d["value_lens"]["moat_durability"][0].pop("quote")
    _, rep = schema.validate(d, TRANSCRIPT, 600)
    assert not rep.ok
    assert any("value_lens.moat_durability[0]" in e and "quote" in e for e in rep.errors)


def test_fabricated_lens_quote_counts_toward_wholesale_reject():
    d = _base()
    d["value_lens"]["moat_durability"][0]["quote"] = "ประโยคที่ไม่เคยถูกพูดในคลิปนี้เลย"
    d["management_tone"]["quotes"] = ["อีกประโยคที่แต่งขึ้นมาเอง"]
    _, rep = schema.validate(d, TRANSCRIPT, 600)
    # 2 fabricated anchors out of 3 anchored items -> above the 30% tripwire.
    assert not rep.ok
    assert any("fabrication suspicion" in e for e in rep.errors)


def test_unknown_lens_key_warned_not_fatal():
    d = _base()
    d["value_lens"]["brand_power"] = [
        {"text": "x", "type": "opinion", "quote": ""}
    ]
    _, rep = schema.validate(d, TRANSCRIPT, 600)
    assert rep.ok, rep.errors
    assert any("unknown lens" in w for w in rep.warnings)


def test_bad_tone_label_coerced_with_warning():
    d = _base()
    d["management_tone"]["label"] = "euphoric"
    norm, rep = schema.validate(d, TRANSCRIPT, 600)
    assert rep.ok, rep.errors
    assert norm["management_tone"]["label"] == "mixed"
    assert any("management_tone" in w for w in rep.warnings)


def test_absent_lens_and_tone_stay_backward_compatible():
    d = {"summary": ["ok"], "claims": []}
    norm, rep = schema.validate(d, TRANSCRIPT, 600)
    assert rep.ok, rep.errors
    assert norm["value_lens"] == {}
    assert norm["management_tone"] is None


def test_validate_is_idempotent_on_its_own_output():
    norm1, rep1 = schema.validate(_base(), TRANSCRIPT, 600)
    assert rep1.ok and rep1.quote_fail_count == 0
    norm2, rep2 = schema.validate(norm1, TRANSCRIPT, 600)
    assert rep2.ok, rep2.errors
    assert rep2.quote_fail_count == rep1.quote_fail_count == 0
    assert rep2.claim_count == rep1.claim_count


def test_tone_quote_double_poison_heals():
    d = _base()
    d["management_tone"]["quotes"] = [
        {"quote": "{'quote': 'จะซื้อหุ้นคืนถ้าราคาต่ำกว่ามูลค่า', 'verification': 'quote_verified'}",
         "verification": "quote_not_found"}
    ]
    norm, rep = schema.validate(d, TRANSCRIPT, 600)
    assert rep.ok, rep.errors
    assert norm["management_tone"]["quotes"][0]["verification"] == "quote_verified"
    assert rep.quote_fail_count == 0
