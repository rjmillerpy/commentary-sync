import time

from app.clock import service


def test_reads_the_given_clock() -> None:
    assert service.server_time(lambda: 1_792_342_800.5).now == 1_792_342_800.5


def test_defaults_to_the_system_clock() -> None:
    before = time.time()
    assert before <= service.server_time().now <= time.time()
