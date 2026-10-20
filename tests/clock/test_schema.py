from app.clock.schema import ServerTime


def test_server_time_is_epoch_seconds() -> None:
    assert ServerTime(now=1_792_342_800.25).model_dump() == {"now": 1_792_342_800.25}
