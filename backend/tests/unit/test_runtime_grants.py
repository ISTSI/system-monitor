import pytest

from inspector.database import validate_runtime_grants


def test_exact_hyphenated_schema_dml_and_authentication_material_are_safe():
    validate_runtime_grants(
        [
            "GRANT USAGE ON *.* TO `app`@`%` IDENTIFIED BY PASSWORD 'synthetic-auth-value'",
            "GRANT SELECT, INSERT, UPDATE, DELETE ON `system-monitor`.* TO `app`@`%`",
        ],
        "system-monitor",
    )


@pytest.mark.parametrize(
    "statement",
    [
        "GRANT ALL PRIVILEGES ON `system-monitor`.* TO `app`@`%`",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON *.* TO `app`@`%`",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON `other`.* TO `app`@`%`",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON `system-monitor`.* TO `app`@`%` WITH GRANT OPTION",
        "GRANT SELECT ON `system-monitor`.* TO `app`@`%`",
        "GRANT `some_role` TO `app`@`%`",
    ],
)
def test_privileged_wrong_schema_incomplete_and_role_grants_fail_closed(statement):
    with pytest.raises(RuntimeError) as error:
        validate_runtime_grants([statement], "system-monitor")
    assert "synthetic-auth-value" not in str(error.value)


def test_underscore_schema_grants_are_exact_and_never_wildcards():
    statement = "GRANT SELECT, INSERT, UPDATE, DELETE ON `system_inspector`.* TO `app`@`%`"
    with pytest.raises(RuntimeError):
        validate_runtime_grants([statement], "system_inspector")
    validate_runtime_grants(
        [statement.replace("system_inspector", r"system\_inspector")], "system_inspector"
    )
