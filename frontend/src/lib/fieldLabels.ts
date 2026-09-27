import type { EntityField, TemplateFieldDef } from "../api/types";

/**
 * Ключ → человекочитаемая подпись. Используется, когда ни шаблон, ни сама
 * сущность подписи не несут. Формулировки совпадают с тем, что печатают
 * встроенные шаблоны наверху листа (см.
 * backend/src/loregraph/templates/builtins.py), чтобы список полей в панели
 * доступа читался так же, как лист над ним.
 *
 * Намеренно словарь в коде, а не запись в locales/*.json: подписи встроенных
 * шаблонов уезжают с бэкенда по-русски и только по-русски, а значит
 * переведённый здесь словарь разошёлся бы с листом в любой локали, кроме
 * одной. Общий переезд в i18n — отдельная задача.
 */
const FIELD_LABELS: Record<string, string> = {
  // header band / basics
  level: "Уровень",
  ac: "Класс доспеха",
  hp: "Хиты",
  max_hp: "Макс. хиты",
  temp_hp: "Временные хиты",
  speed: "Скорость",
  proficiency: "Бонус владения",
  experience: "Опыт",
  hit_die: "Кость хитов",
  hit_dice_current: "Осталось костей",
  exhaustion: "Истощение",
  inspiration: "Вдохновение",
  player_name: "Имя игрока",

  // identity
  class: "Класс",
  archetype: "Архетип",
  ancestry: "Происхождение",
  background: "Предыстория",
  alignment: "Мировоззрение",

  // abilities
  str: "Сила",
  dex: "Ловкость",
  con: "Телосложение",
  int: "Интеллект",
  wis: "Мудрость",
  cha: "Харизма",

  // saving throws
  prof_save_str: "Спасбросок: Сила",
  prof_save_dex: "Спасбросок: Ловкость",
  prof_save_con: "Спасбросок: Телосложение",
  prof_save_int: "Спасбросок: Интеллект",
  prof_save_wis: "Спасбросок: Мудрость",
  prof_save_cha: "Спасбросок: Харизма",

  // skills
  prof_acrobatics: "Акробатика",
  prof_animal_handling: "Уход за животными",
  prof_arcana: "Магия",
  prof_athletics: "Атлетика",
  prof_deception: "Обман",
  prof_history: "История",
  prof_insight: "Проницательность",
  prof_intimidation: "Запугивание",
  prof_investigation: "Анализ",
  prof_medicine: "Медицина",
  prof_nature: "Природа",
  prof_perception: "Восприятие",
  prof_performance: "Выступление",
  prof_persuasion: "Убеждение",
  prof_religion: "Религия",
  prof_sleight_of_hand: "Ловкость рук",
  prof_stealth: "Скрытность",
  prof_survival: "Выживание",

  // spells
  caster_class: "Класс заклинателя",
  spell_ability: "Базовая характеристика",
  spell_save_dc: "Сложность спасброска",
  spell_attack: "Бонус атаки",
  spell_slots: "Ячейки заклинаний",
  spells: "Заклинания",

  // coins
  coins_pp: "ПМ",
  coins_gp: "ЗМ",
  coins_ep: "ЭМ",
  coins_sp: "СМ",
  coins_cp: "ММ",

  // biography
  traits: "Черты характера",
  personality: "Черты характера",
  ideals: "Идеалы",
  bonds: "Привязанности",
  flaws: "Слабости",
  backstory: "История",

  // equipment / features
  equipment: "Снаряжение",
  weapons: "Оружие",
  attacks: "Оружие",
  extra_features: "Дополнительные способности",
  other_proficiencies: "Прочие владения и языки",
  allies: "Союзники",
  quests: "Квесты",

  // media
  avatar_url: "Портрет",
  portrait: "Портрет",
};

/** "my_custom_key" → "My custom key". Последний resort для ключа, о котором
 * ничего не знает ни один словарь и ни один шаблон — кастомное поле, которое
 * ДМ набрал руками. Не переводим и не капитализируем каждое слово: на этом
 * этапе мы называем чужой ключ, а не своё понятие. */
function prettifyKey(key: string): string {
  const spaced = key.replace(/[_-]+/g, " ").trim();
  if (!spaced) return key;
  return spaced[0].toUpperCase() + spaced.slice(1);
}

/**
 * Одна подпись для одного поля. Порядок разрешения совпадает с тем, что
 * делает SheetRenderer наверху листа, поэтому одно и то же поле читается
 * одинаково и там, и здесь:
 *
 *   1. подпись из field_def шаблона — побеждает, потому что именно её
 *      рендерит верх листа;
 *   2. собственная подпись поля (`EntityField.label`) — override от
 *      LSS-импортёра, актуальный для скиллов;
 *   3. встроенный словарь выше;
 *   4. prettifyKey.
 */
export function fieldLabelFor(
  field: Pick<EntityField, "key" | "label">,
  defsByKey?: Map<string, TemplateFieldDef>,
): string {
  const fromTemplate = defsByKey?.get(field.key)?.label?.trim();
  if (fromTemplate) return fromTemplate;

  const fromSource = field.label?.trim();
  if (fromSource) return fromSource;

  return FIELD_LABELS[field.key] ?? prettifyKey(field.key);
}