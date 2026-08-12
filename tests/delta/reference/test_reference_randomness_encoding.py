from trace_reference.generation.randomness import (
    encode_keyed_parts,
    uniform_micros,
    uniform_micros_encoded,
)


def test_encoded_keyed_draws_are_byte_equivalent() -> None:
    seed = 1_234_567
    parts = (187_200, "hazard_response", "RS-0123456789abcdef")

    assert uniform_micros(seed, "delta-reference-randomness-v1", *parts) == (
        uniform_micros_encoded(
            seed,
            "delta-reference-randomness-v1",
            encode_keyed_parts(parts[0]),
            encode_keyed_parts(*parts[1:]),
        )
    )
