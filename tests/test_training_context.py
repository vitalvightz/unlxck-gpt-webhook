from dataclasses import fields

from fightcamp.training_context import TrainingContext


def test_training_context_has_single_declared_support_day_fields():
    field_names = [item.name for item in fields(TrainingContext)]

    assert field_names.count("training_split") == 1
    assert field_names.count("hard_sparring_days") == 1
    assert field_names.count("support_work_days") == 1
    assert field_names.count("technical_skill_days") == 1
