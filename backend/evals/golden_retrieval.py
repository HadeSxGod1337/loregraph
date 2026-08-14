"""Golden retrieval dataset for run_retrieval_eval.py.

Each case is a small, self-contained lore corpus (its own isolated project
namespace) plus a query and human-assigned relevance grades (0 = irrelevant,
1 = relevant, 2 = the entity the query is really about). Cases mix Russian
and English campaigns, and one deliberately queries in a different language
than the entity it targets — Loregraph's default embedder is multilingual
(llm/embeddings.py, paraphrase-multilingual-MiniLM-L12-v2) precisely because
DMs write lore in whichever language they run their table in, so retrieval
quality across and within languages is what this dataset is checking.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from loregraph.schemas.entity import EntityFieldOut, EntityOut, FieldType

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _entity(
    entity_id: str,
    project_id: str,
    entity_type: str,
    title: str,
    **text_fields: str,
) -> EntityOut:
    return EntityOut(
        id=entity_id,
        project_id=project_id,
        type=entity_type,
        title=title,
        fields=[
            EntityFieldOut(key=key, field_type=FieldType.TEXT, value=value)
            for key, value in text_fields.items()
        ],
        icon=None,
        created_at=_NOW,
        updated_at=_NOW,
    )


@dataclass(frozen=True)
class GoldenQuery:
    case_id: str
    project_id: str
    query: str
    entities: list[EntityOut]
    relevance: dict[str, int]  # entity_id -> grade; ids absent here are 0
    k: int


GOLDEN_QUERIES: list[GoldenQuery] = [
    GoldenQuery(
        case_id="ru_blacksmith_ally",
        project_id="ru_barovia",
        query="Кто из союзников гильдии может починить оружие партии?",
        entities=[
            _entity(
                "npc_mira",
                "ru_barovia",
                "npc",
                "Мира Кузнец",
                role="кузнец",
                bio="Союзник гильдии ремесленников, чинит оружие и доспехи "
                "в Норвинтере.",
            ),
            _entity(
                "npc_ilya",
                "ru_barovia",
                "npc",
                "Илья Трактирщик",
                role="трактирщик",
                bio="Держит таверну «Ржавый котёл», знает все слухи города, не боец.",
            ),
            _entity(
                "loc_forge",
                "ru_barovia",
                "location",
                "Кузница Миры",
                description="Мастерская, где Мира Кузнец чинит снаряжение "
                "искателей приключений.",
            ),
            _entity(
                "faction_guild",
                "ru_barovia",
                "faction",
                "Гильдия ремесленников",
                description="Союз мастеровых Норвинтера, в который входит Мира Кузнец.",
            ),
        ],
        relevance={"npc_mira": 2, "loc_forge": 1, "faction_guild": 1},
        k=2,
    ),
    GoldenQuery(
        case_id="en_dragon_threat",
        project_id="en_ashfall",
        query="What is the biggest threat to the town of Ashfall right now?",
        entities=[
            _entity(
                "npc_kael",
                "en_ashfall",
                "npc",
                "Kael Draven",
                role="mayor",
                bio="Mayor of Ashfall, desperate to hide the dragon sighting "
                "from the council.",
            ),
            _entity(
                "monster_pyros",
                "en_ashfall",
                "monster",
                "Pyros the Ashwing",
                bio="An adult red dragon lairing in the caldera above "
                "Ashfall, demanding tribute.",
            ),
            _entity(
                "loc_tavern",
                "en_ashfall",
                "location",
                "The Sooty Anvil",
                description="A tavern where rumors about strange ash-falls circulate.",
            ),
            _entity(
                "npc_merchant",
                "en_ashfall",
                "npc",
                "Rina the Trader",
                bio="A traveling merchant passing through Ashfall, "
                "unrelated to the dragon plot.",
            ),
        ],
        relevance={"monster_pyros": 2, "npc_kael": 1},
        k=2,
    ),
    GoldenQuery(
        case_id="ru_en_mixed_faction_leader",
        query="Кто возглавляет фракцию 'Пепельный картель' и какой у него CR?",
        project_id="ru_mixed",
        entities=[
            _entity(
                "npc_dread",
                "ru_mixed",
                "npc",
                "Дред Ольшанов",
                role="лидер фракции",
                bio="Возглавляет 'Пепельный картель', CR 8, boss encounter "
                "финала первого акта.",
            ),
            _entity(
                "faction_cartel",
                "ru_mixed",
                "faction",
                "Пепельный картель",
                description="Контрабандистская фракция под руководством "
                "Дреда Ольшанова.",
            ),
            _entity(
                "npc_rival",
                "ru_mixed",
                "npc",
                "Соня Ветрова",
                role="соперница",
                bio="Конкурирующая торговка, враждует с картелем, но не входит в него.",
            ),
        ],
        relevance={"npc_dread": 2, "faction_cartel": 1},
        k=2,
    ),
    GoldenQuery(
        case_id="cross_lingual_query_ru_entity",
        # English query, but the target entity's text is Russian-only —
        # checks whether the multilingual embedder actually bridges
        # languages rather than just tokenizing both without aligning them.
        query="Who is the assassin hunting the royal family?",
        project_id="cross_lingual",
        entities=[
            _entity(
                "npc_assassin",
                "cross_lingual",
                "npc",
                "Тень Ирис",
                bio="Наёмная убийца, охотится на членов королевской семьи "
                "по заказу картеля.",
            ),
            _entity(
                "npc_baker",
                "cross_lingual",
                "npc",
                "Пекарь Олег",
                bio="Печёт хлеб на главной площади, к политике отношения не имеет.",
            ),
            _entity(
                "loc_castle",
                "cross_lingual",
                "location",
                "Королевский замок",
                description="Резиденция королевской семьи, охраняется "
                "усиленной стражей.",
            ),
        ],
        relevance={"npc_assassin": 2, "loc_castle": 1},
        k=2,
    ),
    GoldenQuery(
        case_id="distractor_heavy_similar_npcs",
        # Six near-duplicate "guard" NPCs plus the one that actually
        # answers the query — stresses ranking precision, not just recall.
        query="Which guard is secretly loyal to the thieves' guild?",
        project_id="distractors",
        entities=[
            _entity(
                "npc_guard_corrupt",
                "distractors",
                "npc",
                "Guard Tomas",
                role="city guard",
                bio="Outwardly a loyal city guard, secretly feeds patrol "
                "schedules to the thieves' guild.",
            ),
            *(
                _entity(
                    f"npc_guard_{i}",
                    "distractors",
                    "npc",
                    f"Guard {name}",
                    role="city guard",
                    bio=f"A dutiful city guard on the north wall named {name}, "
                    "nothing unusual about them.",
                )
                for i, name in enumerate(
                    ["Bren", "Halla", "Otto", "Sven", "Yara"], start=1
                )
            ),
        ],
        relevance={"npc_guard_corrupt": 2},
        k=3,
    ),
    GoldenQuery(
        case_id="namesakes_by_bare_name",
        # Three unrelated characters share one given name. The query is the
        # bare name, so every one of them is the answer — a semantic ranker
        # that returns "the most Egor-like Egor" has failed this question.
        query="Егор",
        project_id="namesakes",
        entities=[
            _entity(
                "npc_egor_mage",
                "namesakes",
                "npc",
                "Егор",
                summary="Молодой маг-артефактор из маленького городка.",
            ),
            _entity(
                "npc_egor_senior",
                "namesakes",
                "npc",
                "Егор",
                summary="Старший товарищ по школе, связан через Александра.",
            ),
            _entity(
                "npc_egor_emperor",
                "namesakes",
                "npc",
                "Егор",
                summary="Высокопоставленный правитель, держит договор с кланом.",
            ),
            _entity(
                "npc_mira",
                "namesakes",
                "npc",
                "Мира Кузнец",
                summary="Кузнец, чинит оружие и доспехи.",
            ),
        ],
        relevance={
            "npc_egor_mage": 2,
            "npc_egor_senior": 2,
            "npc_egor_emperor": 2,
        },
        k=4,
    ),
    GoldenQuery(
        case_id="fact_in_the_tail_of_a_long_entity",
        # The distinguishing fact sits far past the local embedder's ~128-token
        # input window. Before entity chunking this was structurally
        # unreachable: the tail was dropped before embedding, silently.
        query="Кто хранит ключ от старой шахты?",
        project_id="long_entity",
        entities=[
            _entity(
                "npc_keeper",
                "long_entity",
                "npc",
                "Тобиас Верн",
                bio=" ".join(
                    [
                        "Родился в семье лесорубов и всю жизнь провёл в "
                        "предгорьях, ничем не выделяясь среди соседей."
                    ]
                    * 12
                ),
                secret="Единственный, у кого остался ключ от старой шахты.",
            ),
            _entity(
                "npc_miner",
                "long_entity",
                "npc",
                "Гарен",
                bio="Бывший шахтёр, давно не спускался под землю.",
            ),
            _entity(
                "loc_mine",
                "long_entity",
                "location",
                "Старая шахта",
                bio="Заброшенная выработка к северу от посёлка, вход завален.",
            ),
        ],
        relevance={"npc_keeper": 2, "loc_mine": 1},
        k=3,
    ),
    GoldenQuery(
        case_id="rare_proper_name_among_many",
        # A name that appears exactly once, in a project big enough that a
        # dense-only ranker has no reason to float it. This is the lexical
        # contour's regression (services/lore_search.py).
        query="Кассивелаун",
        project_id="crowded",
        entities=[
            _entity(
                "npc_target",
                "crowded",
                "npc",
                "Кассивелаун",
                summary="Немолодой картограф, почти не покидает архив.",
            ),
            *(
                _entity(
                    f"npc_filler_{i}",
                    "crowded",
                    "npc",
                    f"Житель {i}",
                    summary="Обычный горожанин, торгует на рынке, "
                    "ничем не примечателен.",
                )
                for i in range(30)
            ),
        ],
        relevance={"npc_target": 2},
        k=3,
    ),
]
