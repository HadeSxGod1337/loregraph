"""Golden dataset for run_tool_choice_eval.py: question -> the tool that can
actually answer it.

This is the contour the retrieval metrics in golden_retrieval.py structurally
cannot see. "Сколько егоров в мире" has no ranking answer at all — a perfect
top-k is still a wrong answer if the question was a count — and a relationship
question is unanswerable from entity text no matter how well it ranks. What
decides whether the game master gets a true answer is which tool the model
reaches for, so that is what this set measures.

Cases carry a small world, so a run can optionally check the answer text too;
the primary metric is only the tool choice.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from loregraph.schemas.edge import EdgeOut
from loregraph.schemas.entity import EntityFieldOut, EntityOut, FieldType

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
PROJECT_ID = "tool_choice"


def _entity(entity_id: str, entity_type: str, title: str, **fields: str) -> EntityOut:
    return EntityOut(
        id=entity_id,
        project_id=PROJECT_ID,
        type=entity_type,
        title=title,
        fields=[
            EntityFieldOut(key=key, field_type=FieldType.TEXT, value=value)
            for key, value in fields.items()
        ],
        icon=None,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _edge(edge_id: str, source: str, target: str, edge_type: str) -> EdgeOut:
    return EdgeOut(
        id=edge_id,
        project_id=PROJECT_ID,
        source_entity_id=source,
        target_entity_id=target,
        type=edge_type,
        label=None,
        created_at=_NOW,
    )


@dataclass(frozen=True)
class ToolChoiceCase:
    case_id: str
    question: str
    # Any one of these counts as correct — several tools can be a defensible
    # first move (get_entity_graph vs get_entity_details for "is A hostile to
    # B"), and the failure being measured is reaching for search_lore instead.
    acceptable_tools: frozenset[str]
    entities: list[EntityOut]
    edges: list[EdgeOut] = field(default_factory=list)
    # For propose_changes cases only: the exact set of existing-entity titles
    # that must appear in the call's target_entity_ids. Picking the right tool
    # is no longer enough once create and edit share one tool — the screenshot
    # bug was choosing the right INTENT (change the world) but the wrong SHAPE
    # (create vs edit). None means "not checked" (read-tool cases). An empty
    # set means "must name no targets" (a pure creation).
    expected_target_titles: frozenset[str] | None = None


_EYELESS = _entity("fac_eyeless", "faction", "Безглазые", leader="Ортус")
_SIXWINGED = _entity("fac_sixwinged", "faction", "Шестикрылые")
_EGORS = [
    _entity("npc_egor_1", "npc", "Егор", summary="Молодой маг-артефактор."),
    _entity("npc_egor_2", "npc", "Егор", summary="Старший товарищ по школе."),
    _entity("npc_egor_3", "npc", "Егор", summary="Высокопоставленный правитель."),
]
_MIRA = _entity("npc_mira", "npc", "Мира Кузнец", role="кузнец")
_ORDER = _entity(
    "fac_order",
    "faction",
    "Орден Серебряного Пламени",
    creed="Орден паладинов, выжигающий скверну огнём.",
)
_ASHEN = _entity(
    "fac_ashen",
    "faction",
    "Пепельный культ",
    summary="Культ, поклоняющийся тлению; давние враги Ордена.",
)


CASES: list[ToolChoiceCase] = [
    ToolChoiceCase(
        case_id="count_namesakes_ru",
        question="сколько егоров в мире?",
        acceptable_tools=frozenset({"list_entities"}),
        entities=[*_EGORS, _MIRA],
    ),
    ToolChoiceCase(
        case_id="count_by_type_ru",
        question="сколько всего фракций в мире?",
        acceptable_tools=frozenset({"list_entities"}),
        entities=[_EYELESS, _SIXWINGED, _MIRA],
    ),
    ToolChoiceCase(
        case_id="enumerate_all_en",
        question="List every faction in the world.",
        acceptable_tools=frozenset({"list_entities"}),
        entities=[_EYELESS, _SIXWINGED, _MIRA],
    ),
    ToolChoiceCase(
        case_id="verify_relationship_ru",
        # The screenshot case: the edge exists, neither entity's fields
        # mention it, and the assistant used to deny it outright.
        question="перепроверь связь enemy_of между Шестикрылыми и Безглазыми",
        acceptable_tools=frozenset({"get_entity_graph", "get_entity_details"}),
        entities=[_EYELESS, _SIXWINGED],
        edges=[_edge("edge_1", "fac_sixwinged", "fac_eyeless", "enemy_of")],
    ),
    ToolChoiceCase(
        case_id="allies_of_ru",
        question="кто союзники Безглазых?",
        acceptable_tools=frozenset({"get_entity_graph", "get_entity_details"}),
        entities=[_EYELESS, _MIRA],
        edges=[_edge("edge_2", "npc_mira", "fac_eyeless", "ally_of")],
    ),
    ToolChoiceCase(
        case_id="edit_add_fields_ru",
        # Reported by a game master (the screenshot case): the assistant
        # answered "these details were added to the world" and nothing had
        # changed — it created duplicate entities and links instead of editing
        # Егор. With one unified write tool the routing question is simpler:
        # the assistant must reach propose_changes AND name Егор as a target,
        # so the pipeline edits him rather than cloning him.
        question="Придумай кто такой этот Егор и добавь поля ему",
        acceptable_tools=frozenset({"propose_changes"}),
        # Exactly one Егор: with the three namesakes of the counting cases the
        # right move is a clarifying question, and the case would be testing
        # ambiguity handling rather than edit routing.
        entities=[_EGORS[0], _MIRA],
        # The tool choice alone is no longer the whole story — the target must
        # be named. Checked by the eval runner when present (see below).
        expected_target_titles=frozenset({"Егор"}),
    ),
    ToolChoiceCase(
        case_id="edit_rewrite_field_ru",
        question="Перепиши роль Миры покороче",
        acceptable_tools=frozenset({"propose_changes"}),
        entities=[_MIRA],
        expected_target_titles=frozenset({"Мира Кузнец"}),
    ),
    ToolChoiceCase(
        case_id="brainstorm_smuggler_network_ru",
        # The behavior change this feature is about: "придумай …" with no "add"
        # is a request for IDEAS, not a database mutation. It used to route to
        # propose_changes; it must now brainstorm, writing nothing.
        question="Придумай контрабандистскую сеть в порту",
        acceptable_tools=frozenset({"brainstorm_lore"}),
        entities=[_MIRA],
    ),
    ToolChoiceCase(
        case_id="brainstorm_options_to_choose_ru",
        # "Give me options, I'll pick" is pure brainstorm — no proposal until
        # the game master chooses one on a later turn.
        question="Предложи пять вариантов злодея, я потом выберу",
        acceptable_tools=frozenset({"brainstorm_lore"}),
        entities=[_MIRA],
    ),
    ToolChoiceCase(
        case_id="brainstorm_enemy_for_order_ru",
        # Creative request that should build on existing canon (the Order) but
        # still NOT mutate: brainstorm an enemy, grounded in a real faction.
        question="Придумай врага для Ордена Серебряного Пламени",
        acceptable_tools=frozenset({"brainstorm_lore"}),
        entities=[_ORDER, _MIRA],
    ),
    ToolChoiceCase(
        case_id="create_new_entity_with_add_is_propose_ru",
        # Same creative prompt as the brainstorm case, but "и добавь …" makes it
        # a mutation — propose_changes, carrying NO existing target (a pure
        # creation, not an edit of something that exists).
        question="Придумай контрабандистскую сеть в порту и добавь её в мир",
        acceptable_tools=frozenset({"propose_changes"}),
        entities=[_MIRA],
        expected_target_titles=frozenset(),
    ),
    ToolChoiceCase(
        case_id="create_explicit_is_propose_ru",
        question="Создай контрабандистскую сеть в порту",
        acceptable_tools=frozenset({"propose_changes"}),
        entities=[_MIRA],
        expected_target_titles=frozenset(),
    ),
    ToolChoiceCase(
        case_id="add_enemy_for_order_is_propose_ru",
        # Creative + mutation grounded in an existing entity: invent an enemy
        # AND add it, connecting it to the Order — propose_changes must name the
        # Order as the existing target so the new enemy links to the real one.
        question="Придумай врага для Ордена Серебряного Пламени и добавь его",
        acceptable_tools=frozenset({"propose_changes"}),
        entities=[_ORDER, _MIRA],
        expected_target_titles=frozenset({"Орден Серебряного Пламени"}),
    ),
    ToolChoiceCase(
        case_id="enemy_of_order_is_graph_ru",
        # The read counterpart to the two Order cases above: a FACT question is
        # answered from the graph, never invented.
        question="Кто враг Ордена Серебряного Пламени?",
        acceptable_tools=frozenset({"get_entity_graph", "get_entity_details"}),
        entities=[_ORDER, _ASHEN],
        edges=[_edge("edge_order_enemy", "fac_order", "fac_ashen", "enemy_of")],
    ),
    ToolChoiceCase(
        case_id="open_question_stays_semantic_ru",
        # The control: an open "what is out there" question must NOT be
        # dragged onto list_entities by the new rules.
        question="есть ли в мире кто-нибудь, кто умеет чинить оружие?",
        acceptable_tools=frozenset({"search_lore"}),
        entities=[_MIRA, _EYELESS],
    ),
    ToolChoiceCase(
        case_id="link_two_existing_ru",
        # A pure relationship request is the same unified tool, and both
        # entities are its targets — never propose two throwaway entities.
        question="свяжи Миру с Безглазыми как союзника",
        acceptable_tools=frozenset({"propose_changes"}),
        entities=[_MIRA, _EYELESS],
        expected_target_titles=frozenset({"Мира Кузнец", "Безглазые"}),
    ),
]
