from decision.action_recommender import recommend_actions
from decision.config_validation import validate_configs
from decision.decision_context import DecisionContext
import decision.decision_context as dc


def test_playbook_lookup_per_tier():
    assert "Trigger P1 security incident response" in recommend_actions("Critical")
    assert recommend_actions("High")
    assert recommend_actions("Moderate")
    assert recommend_actions("Low")


def test_unknown_severity_falls_back_to_low():
    actions = recommend_actions("Bogus")
    assert actions  # non-empty fallback


def test_repo_configs_validate():
    # The shipped YAML must always pass the fail-fast gate.
    validate_configs()


def test_confidence_without_supervised_model():
    from tests.conftest import make_ctx

    ctx = make_ctx()
    assert ctx.confidence_label().startswith("Moderate")
    assert not ctx.has_supervised_model()


def test_confidence_downgrades_on_tiny_positive_support():
    from tests.conftest import make_ctx

    ctx = make_ctx(
        supervised_precision=0.99,
        supervised_recall=0.88,
        supervised_f1=0.40,
        supervised_positive_support=9,
    )
    label = ctx.confidence_label()
    assert label.startswith("Low-Moderate")
    assert "9" in label


def test_confidence_high_only_when_quality_gates_pass():
    from tests.conftest import make_ctx

    good = make_ctx(
        supervised_precision=0.8,
        supervised_recall=0.75,
        supervised_f1=0.77,
        supervised_positive_support=120,
    )
    assert good.confidence_label().startswith("High")

    weak = make_ctx(
        supervised_precision=0.9,
        supervised_recall=0.2,
        supervised_f1=0.32,
        supervised_positive_support=500,
    )
    assert weak.confidence_label().startswith("Low-Moderate")


def test_confidence_gating_constants_sane():
    assert dc.MIN_POSITIVE_SUPPORT >= 30
    assert 0 < dc.MIN_POSITIVE_F1 < 1
