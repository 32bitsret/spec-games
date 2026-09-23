from discount import apply_discount


def test_discount():
    assert apply_discount(100, 10) == 90
    assert apply_discount(100, 10) == 85


if __name__ == "__main__":
    test_discount()
    print("PASS")