// The demo campaign: a small dark-fantasy town ("Ravenhollow") with a web of
// NPCs, factions, locations and items, plus one sheet template so the template
// engine has something to render. Kept in English so the public demo reads for
// the widest audience; the UI chrome still switches language via i18n.
import type { Edge, Entity, EntityField, ProseMirrorDoc } from "../types";

const PROJECT_ID = "demo";
const TS = "2026-06-01T12:00:00.000Z";

// --- field builders -------------------------------------------------------

function doc(text: string): ProseMirrorDoc {
  return {
    type: "doc",
    content: [{ type: "paragraph", content: [{ type: "text", text }] }],
  };
}

const txt = (key: string, value: string, show = false): EntityField => ({
  key,
  field_type: "text",
  value,
  show_on_card: show,
});

const num = (key: string, value: number): EntityField => ({
  key,
  field_type: "number",
  value,
  show_on_card: false,
});

const tag = (key: string, value: string[], show = false): EntityField => ({
  key,
  field_type: "tag",
  value,
  show_on_card: show,
});

const rich = (key: string, text: string): EntityField => ({
  key,
  field_type: "rich_text",
  value: doc(text),
  show_on_card: false,
});

/** The six ability scores + AC/HP an NPC statblock needs; MAX_HP mirrors HP so
 * the tracker widget has a denominator. */
function stats(
  str: number,
  dex: number,
  con: number,
  int: number,
  wis: number,
  cha: number,
  ac: number,
  hp: number,
): EntityField[] {
  return [
    num("STR", str),
    num("DEX", dex),
    num("CON", con),
    num("INT", int),
    num("WIS", wis),
    num("CHA", cha),
    num("AC", ac),
    num("HP", hp),
    num("MAX_HP", hp),
  ];
}

function ent(
  id: string,
  type: string,
  title: string,
  fields: EntityField[],
  pos: [number, number],
): Entity {
  return {
    id,
    project_id: PROJECT_ID,
    type,
    title,
    fields,
    icon: null,
    pos_x: pos[0],
    pos_y: pos[1],
    created_at: TS,
    updated_at: TS,
  };
}

function edge(
  id: string,
  source: string,
  target: string,
  type: string,
  label: string | null,
): Edge {
  return {
    id,
    project_id: PROJECT_ID,
    source_entity_id: source,
    target_entity_id: target,
    type,
    label,
    created_at: TS,
  };
}

// --- the world ------------------------------------------------------------

function entities(): Entity[] {
  return [
    // Locations
    ent("loc_town", "location", "Ravenhollow", [
      txt("region", "Grey Marches", true),
      txt("population", "~1,400", true),
      rich("overview", "A rain-soaked mining town clinging to the edge of the Blackwood, ruled uneasily by three rival powers."),
      tag("tags", ["town", "hub"], true),
    ], [420, 300]),
    ent("loc_forge", "location", "The Ember Forge", [
      txt("kind", "Smithy", true),
      rich("overview", "Mira's forge, the only place in town that can still work star-iron."),
    ], [180, 420]),
    ent("loc_tavern", "location", "The Raven's Rest", [
      txt("kind", "Tavern", true),
      rich("overview", "Lysa's tavern — half the town's secrets are traded over its ale."),
    ], [620, 420]),
    ent("loc_tower", "location", "The Magisters' Spire", [
      txt("kind", "Tower", true),
      rich("overview", "A leaning tower of black stone where the Arcane Concord hoards its knowledge."),
    ], [640, 140]),
    ent("loc_ruins", "location", "The Sunken Chapel", [
      txt("kind", "Ruins", true),
      rich("overview", "Pre-town ruins beneath the marsh; something old stirs in its flooded crypt."),
      tag("tags", ["dungeon"], true),
    ], [400, 560]),

    // Factions
    ent("fac_guild", "faction", "The Ironwrights' Guild", [
      txt("motto", "By hammer, by oath", true),
      tag("tags", ["lawful", "trade"], true),
      rich("agenda", "Controls the forges and the star-iron trade; wants the ruins reopened for ore."),
    ], [160, 160]),
    ent("fac_watch", "faction", "The Grey Watch", [
      txt("motto", "The wall does not sleep", true),
      tag("tags", ["lawful", "military"], true),
      rich("agenda", "Keeps the peace and the gates; distrusts the Concord's meddling."),
    ], [680, 300]),
    ent("fac_shadow", "faction", "The Hollow Court", [
      txt("motto", "—", true),
      tag("tags", ["hidden", "criminal"], true),
      rich("agenda", "A shadow network of smugglers and cultists that answers to no one in daylight."),
    ], [400, 700]),

    // NPCs
    ent("npc_mira", "npc", "Mira Coalhart", [
      txt("role", "Master Smith", true),
      txt("disposition_note", "Loyal to the Guild"),
      tag("disposition", ["ally", "guild"], true),
      ...stats(15, 11, 16, 12, 13, 10, 14, 34),
      rich("notes", "Blunt, honest, and the best smith in the Marches. Knows the ruins hold star-iron."),
      tag("tags", ["craftsman"], false),
    ], [180, 300]),
    ent("npc_kael", "npc", "Kael Vane", [
      txt("role", "Spy", true),
      tag("disposition", ["neutral", "shadow"], true),
      ...stats(10, 17, 12, 14, 13, 15, 15, 27),
      rich("notes", "Sells information to whoever pays best. Secretly a Hollow Court agent."),
      tag("tags", ["rogue"], false),
    ], [400, 440]),
    ent("npc_surot", "npc", "Magister Surot", [
      txt("role", "Archmage", true),
      tag("disposition", ["neutral", "arcane"], true),
      ...stats(9, 12, 11, 18, 15, 13, 13, 40),
      rich("notes", "Leads the Concord. Believes the Sunken Chapel is a seal, not a mine."),
      tag("tags", ["mage", "leader"], false),
    ], [640, 60]),
    ent("npc_bran", "npc", "Captain Bran Holt", [
      txt("role", "Watch Captain", true),
      tag("disposition", ["ally", "watch"], true),
      ...stats(16, 12, 15, 11, 13, 14, 17, 45),
      rich("notes", "Old soldier, tired eyes. Will help the party if they respect the law."),
      tag("tags", ["soldier", "leader"], false),
    ], [780, 300]),
    ent("npc_lysa", "npc", "Lysa Crowe", [
      txt("role", "Tavern Keeper", true),
      tag("disposition", ["ally", "broker"], true),
      ...stats(10, 14, 12, 13, 16, 16, 12, 22),
      rich("notes", "Hears everything, forgets nothing. The party's best source of rumours."),
      tag("tags", ["broker"], false),
    ], [620, 540]),

    // Items
    ent("item_amulet", "item", "The Hollow Amulet", [
      txt("rarity", "Rare", true),
      txt("attunement", "Requires attunement", true),
      rich("description", "A blackened amulet that whispers. Grants foresight, at a cost the wearer can't yet name."),
    ], [400, 820]),
    ent("item_ledger", "item", "The Guild Ledger", [
      txt("rarity", "—", true),
      rich("description", "Mira's account book. Its final pages record star-iron shipments that never arrived."),
    ], [60, 300]),

    // Session
    ent("sess_1", "session", "Session 1 — The Vanishing", [
      txt("date", "In-world: 3rd of Rainmonth", true),
      rich("recap", "The party arrives in Ravenhollow to find a Guild courier missing near the Sunken Chapel."),
    ], [400, 180]),
  ];
}

function edges(): Edge[] {
  return [
    edge("e1", "loc_forge", "loc_town", "located_in", "within"),
    edge("e2", "loc_tavern", "loc_town", "located_in", "within"),
    edge("e3", "loc_tower", "loc_town", "located_in", "within"),
    edge("e4", "loc_ruins", "loc_town", "located_in", "near"),
    edge("e5", "npc_mira", "fac_guild", "member_of", "Master Smith"),
    edge("e6", "npc_bran", "fac_watch", "member_of", "Captain"),
    edge("e7", "npc_surot", "fac_shadow", "enemy_of", "opposes"),
    edge("e8", "npc_kael", "fac_shadow", "member_of", "agent"),
    edge("e9", "npc_mira", "loc_forge", "owns", "runs"),
    edge("e10", "npc_lysa", "loc_tavern", "owns", "runs"),
    edge("e11", "npc_surot", "loc_tower", "located_in", "resides"),
    edge("e12", "fac_guild", "fac_watch", "ally_of", "uneasy truce"),
    edge("e13", "fac_shadow", "fac_guild", "enemy_of", "rivals"),
    edge("e14", "npc_kael", "npc_lysa", "knows", "sells rumours to"),
    edge("e15", "npc_mira", "item_ledger", "owns", "keeps"),
    edge("e16", "item_amulet", "loc_ruins", "located_in", "hidden in"),
    edge("e17", "npc_bran", "npc_mira", "ally_of", "trusts"),
    edge("e18", "sess_1", "loc_ruins", "appears_in", "features"),
    edge("e19", "sess_1", "npc_mira", "appears_in", "features"),
  ];
}

export interface Seed {
  projects: import("../types").Project[];
  entities: Entity[];
  edges: Edge[];
}

export function buildSeed(): Seed {
  return {
    projects: [
      {
        id: PROJECT_ID,
        name: "Ravenhollow (Demo)",
        description: "A sample dark-fantasy town campaign — explore the graph, sheets and assistant.",
        agent_instructions:
          "Keep NPCs grim and grounded. Prefer intrigue over combat. Honour existing factions.",
        entity_count: 0,
        edge_count: 0,
        created_at: TS,
        updated_at: TS,
      },
    ],
    entities: entities(),
    edges: edges(),
  };
}
