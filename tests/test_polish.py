"""REQ-012 polish gate tests — the three mechanical guards."""
from earnings_digest import polish

RAW = (
    "[00:00] สวัสดีครับ อืม วันนี้ เอ่อ คุยเรื่องหุ้น PTT ครับ\n"
    "[00:20] รายได้ปีที่แล้ว 3.1 ล้านล้านบาท กำไร 90,000 ล้านบาทครับ\n"
    "[00:45] ตั้งงบลงทุน 89,000 ล้านบาท สำหรับปี 2569 ครับ\n"
    "[01:10] เป้าหมายราคา 38 ถึง 42 บาทครับ\n"
    "[01:30] ธุรกิจก๊าซของเรามีสัญญาระยะยาวกับลูกค้าอุตสาหกรรมรายใหญ่หลายราย "
    "ทำให้กระแสเงินสดค่อนข้างสม่ำเสมอตลอดวัฏจักรพลังงานครับ\n"
    "[01:55] ความเสี่ยงหลักที่เราติดตามใกล้ชิดคือความผันผวนของราคาน้ำมันโลก "
    "และนโยบายตรึงราคาพลังงานของภาครัฐซึ่งกระทบมาร์จิ้นได้ครับ\n"
)

GOOD = (
    "[00:00] สวัสดีครับ วันนี้คุยเรื่องหุ้น PTT ครับ\n"
    "[00:20] รายได้ปีที่แล้ว 3.1 ล้านล้านบาท กำไร 90,000 ล้านบาทครับ\n"
    "[00:45] ตั้งงบลงทุน 89,000 ล้านบาท สำหรับปี 2569 ครับ\n"
    "[01:10] เป้าหมายราคา 38 ถึง 42 บาทครับ\n"
    "[01:30] ธุรกิจก๊าซของเรามีสัญญาระยะยาวกับลูกค้าอุตสาหกรรมรายใหญ่หลายราย "
    "ทำให้กระแสเงินสดค่อนข้างสม่ำเสมอตลอดวัฏจักรพลังงานครับ\n"
    "[01:55] ความเสี่ยงหลักที่เราติดตามใกล้ชิดคือความผันผวนของราคาน้ำมันโลก "
    "และนโยบายตรึงราคาพลังงานของภาครัฐซึ่งกระทบมาร์จิ้นได้ครับ\n"
)


def test_clean_polish_passes():
    rep = polish.validate_polish(RAW, GOOD)
    assert rep.ok, rep.errors


def test_lost_number_rejected():
    bad = GOOD.replace("89,000 ล้านบาท", "งบลงทุนก้อนใหญ่")
    rep = polish.validate_polish(RAW, bad)
    assert not rep.ok
    assert any("G1" in e for e in rep.errors)


def test_altered_number_rejected():
    bad = GOOD.replace("3.1 ล้านล้านบาท", "3.2 ล้านล้านบาท")
    rep = polish.validate_polish(RAW, bad)
    assert not rep.ok
    assert any("G1" in e for e in rep.errors)


def test_comma_reformatting_is_not_alteration():
    ok = GOOD.replace("90,000", "90000")
    rep = polish.validate_polish(RAW, ok)
    assert rep.ok, rep.errors


def test_reordered_markers_rejected():
    lines = GOOD.strip().split("\n")
    bad = "\n".join([lines[0], lines[2], lines[1], lines[3]]) + "\n"
    rep = polish.validate_polish(RAW, bad)
    assert not rep.ok
    assert any("G2" in e for e in rep.errors)


def test_invented_marker_rejected():
    bad = GOOD + "[09:59] สรุปทิ้งท้ายครับ\n"
    rep = polish.validate_polish(RAW, bad)
    assert not rep.ok
    assert any("G2" in e for e in rep.errors)


def test_covert_summary_rejected():
    bad = "[00:00] คุยเรื่อง PTT รายได้ 3.1 ล้านล้านบาท กำไร 90,000 งบ 89,000 ปี 2569 เป้า 38 42\n"
    rep = polish.validate_polish(RAW, bad)
    assert not rep.ok
    assert any("G3" in e for e in rep.errors)


def test_empty_polish_rejected():
    rep = polish.validate_polish(RAW, "  ")
    assert not rep.ok


def test_timestamps_excluded_from_number_guard():
    # Marker digits differ from content digits — dropping ALL markers from the
    # polish must not trip G1 (they are timestamps, not figures)...
    no_markers = "".join(
        line.split("] ", 1)[1] + "\n" for line in GOOD.strip().split("\n")
    )
    rep = polish.validate_polish(RAW, no_markers)
    assert rep.ok, rep.errors
