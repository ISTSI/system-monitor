"""Administrator-controlled manual source confirmation policy."""

import sqlalchemy as sa
from alembic import op

revision = "0008_security_setting"
down_revision = "0007_source_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve the existing explicit-confirmation policy for retained installs.
    op.add_column(
        "application_settings",
        sa.Column(
            "additional_security_measures",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.create_check_constraint(
        op.f("ck_application_settings_additional_security_measures"),
        "application_settings",
        "additional_security_measures IN (0, 1)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_application_settings_additional_security_measures"),
        "application_settings",
        type_="check",
    )
    op.drop_column("application_settings", "additional_security_measures")
