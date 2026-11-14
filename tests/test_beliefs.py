from branch.beliefs import pet_pt_example


def test_sample_shapes():
    b = pet_pt_example()
    s = b.sample(100)
    assert all(len(v) == 100 for v in s.values())
    assert len(b.value_laden_open()) == 1


def test_fix_closes_choice():
    b = pet_pt_example()
    b.choices["allocation"].fix("cut_off")
    assert "allocation" not in [c.name for c in b.open_choices()]
