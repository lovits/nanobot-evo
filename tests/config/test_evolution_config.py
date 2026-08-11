import pytest
from pydantic import ValidationError

from nanobot.config.schema import Config


def test_evolution_is_disabled_by_default() -> None:
    config = Config()

    assert config.evolution.enabled is False
    assert config.evolution.review_every_n_trajectories == 10
    assert config.evolution.review_model_preset is None


def test_evolution_accepts_camel_case_review_preset() -> None:
    config = Config.model_validate(
        {
            "evolution": {
                "enabled": True,
                "reviewModelPreset": "review",
            }
        }
    )

    assert config.evolution.enabled is True
    assert config.evolution.review_model_preset == "review"


def test_evolution_accepts_snake_case_review_preset() -> None:
    config = Config.model_validate(
        {
            "evolution": {
                "review_model_preset": "review",
            }
        }
    )

    assert config.evolution.review_model_preset == "review"


def test_evolution_accepts_supported_review_intervals() -> None:
    camel = Config.model_validate(
        {"evolution": {"reviewEveryNTrajectories": 5}}
    )
    snake = Config.model_validate(
        {"evolution": {"review_every_n_trajectories": 100}}
    )

    assert camel.evolution.review_every_n_trajectories == 5
    assert snake.evolution.review_every_n_trajectories == 100


@pytest.mark.parametrize("value", [0, 7, 50, 101])
def test_evolution_rejects_unsupported_review_intervals(value: int) -> None:
    with pytest.raises(ValidationError):
        Config.model_validate(
            {"evolution": {"reviewEveryNTrajectories": value}}
        )


def test_evolution_serializes_with_camel_case_fields() -> None:
    config = Config.model_validate(
        {
            "evolution": {
                "enabled": True,
                "review_model_preset": "review",
            }
        }
    )

    dumped = config.model_dump(mode="json", by_alias=True)

    assert dumped["evolution"] == {
        "enabled": True,
        "reviewEveryNTrajectories": 10,
        "reviewModelPreset": "review",
    }
