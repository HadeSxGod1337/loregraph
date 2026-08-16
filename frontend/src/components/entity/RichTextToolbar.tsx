import { useEditorState, type Editor } from "@tiptap/react";
import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";

import { icons, type IconName } from "./richTextIcons";

/** Block formats offered by the "format" dropdown. `level` is only read for
 * headings; the entry order is the order shown in the menu. */
const BLOCK_FORMATS = [
  { id: "paragraph", level: 0 },
  { id: "heading1", level: 1 },
  { id: "heading2", level: 2 },
  { id: "heading3", level: 3 },
  { id: "heading4", level: 4 },
  { id: "blockquote", level: 0 },
  { id: "codeBlock", level: 0 },
] as const;

type BlockFormatId = (typeof BLOCK_FORMATS)[number]["id"];

/** Stacks kept short on purpose: every entry is a value written into the
 * document's `fontFamily` attribute, so it has to survive on any machine that
 * opens the campaign — generic families only, no licensed webfonts. */
const FONT_FAMILIES = [
  { id: "default", value: "" },
  { id: "serif", value: "Georgia, 'Times New Roman', serif" },
  { id: "sans", value: "'Segoe UI', Roboto, Helvetica, Arial, sans-serif" },
  { id: "mono", value: "'JetBrains Mono', 'Courier New', monospace" },
  { id: "fantasy", value: "'Cinzel', 'Palatino Linotype', Palatino, serif" },
] as const;

const FONT_SIZES = ["12px", "14px", "16px", "18px", "24px", "32px"] as const;

const TEXT_COLORS = [
  "#e6e6e6",
  "#9aa0a6",
  "#111111",
  "#c0392b",
  "#d35400",
  "#c9a227",
  "#2e7d32",
  "#1565c0",
  "#6a1b9a",
  "#8d6e63",
] as const;

const HIGHLIGHT_COLORS = [
  "#fff3a3",
  "#ffd6a5",
  "#ffadad",
  "#caffbf",
  "#9bf6ff",
  "#bdb2ff",
  "#ffc6ff",
  "#d9d9d9",
] as const;

const TEXT_ALIGNMENTS = ["left", "center", "right", "justify"] as const;

type TextAlignment = (typeof TEXT_ALIGNMENTS)[number];

const ALIGN_ICONS: Record<TextAlignment, IconName> = {
  left: "alignLeft",
  center: "alignCenter",
  right: "alignRight",
  justify: "alignJustify",
};

const DEFAULT_TABLE = { rows: 3, cols: 3, withHeaderRow: true };

interface ToolbarButtonProps {
  icon: IconName;
  title: string;
  isActive?: boolean;
  disabled?: boolean;
  onClick: () => void;
}

/** Every toolbar control suppresses mousedown: the browser would otherwise
 * move focus out of the editor and collapse the selection the command is
 * about to act on. */
function ToolbarButton({
  icon,
  title,
  isActive = false,
  disabled = false,
  onClick,
}: ToolbarButtonProps) {
  return (
    <button
      type="button"
      className={isActive ? "rich-text-toolbar-btn active" : "rich-text-toolbar-btn"}
      title={title}
      aria-label={title}
      aria-pressed={isActive}
      disabled={disabled}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {icons[icon]}
    </button>
  );
}

interface ToolbarMenuProps {
  icon?: IconName;
  label?: string;
  title: string;
  isActive?: boolean;
  className?: string;
  children: (close: () => void) => ReactNode;
}

function ToolbarMenu({
  icon,
  label,
  title,
  isActive = false,
  className,
  children,
}: ToolbarMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const buttonClass = [
    "rich-text-toolbar-btn",
    label ? "with-label" : "",
    isActive || open ? "active" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="rich-text-menu" ref={rootRef}>
      <button
        type="button"
        className={buttonClass}
        title={title}
        aria-label={title}
        aria-expanded={open}
        aria-haspopup="menu"
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => setOpen((value) => !value)}
      >
        {icon ? icons[icon] : null}
        {label ? <span className="rich-text-menu-label">{label}</span> : null}
        <span className="rich-text-menu-caret">{icons.chevron}</span>
      </button>
      {open ? (
        <div
          className={
            className ? `rich-text-menu-popover ${className}` : "rich-text-menu-popover"
          }
          role="menu"
          onMouseDown={(e) => e.preventDefault()}
        >
          {children(() => setOpen(false))}
        </div>
      ) : null}
    </div>
  );
}

interface MenuItemProps {
  label: ReactNode;
  isActive?: boolean;
  disabled?: boolean;
  onClick: () => void;
}

function MenuItem({ label, isActive = false, disabled = false, onClick }: MenuItemProps) {
  return (
    <button
      type="button"
      role="menuitem"
      className={isActive ? "rich-text-menu-item active" : "rich-text-menu-item"}
      disabled={disabled}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

interface ColorGridProps {
  colors: readonly string[];
  current: string;
  resetLabel: string;
  onPick: (color: string) => void;
  onReset: () => void;
}

function ColorGrid({ colors, current, resetLabel, onPick, onReset }: ColorGridProps) {
  return (
    <>
      <div className="rich-text-color-grid">
        {colors.map((color) => (
          <button
            key={color}
            type="button"
            className={
              color.toLowerCase() === current.toLowerCase()
                ? "rich-text-swatch active"
                : "rich-text-swatch"
            }
            style={{ background: color }}
            title={color}
            aria-label={color}
            onClick={() => onPick(color)}
          />
        ))}
      </div>
      <MenuItem label={resetLabel} onClick={onReset} />
    </>
  );
}

/** Icon + text row for a menu item inside the overflow menu — plain text
 * reads fine in the small always-visible toolbar buttons, but a flat list of
 * bare labels in a dropdown is harder to scan than one with icons. */
function iconLabel(icon: IconName, text: string): ReactNode {
  return (
    <span className="rich-text-menu-icon-item">
      {icons[icon]}
      {text}
    </span>
  );
}

/** The current block format, as one id — a heading and a code block can never
 * both hold the cursor, so the dropdown shows a single value. */
function currentBlockFormat(editor: Editor): BlockFormatId {
  if (editor.isActive("codeBlock")) return "codeBlock";
  if (editor.isActive("blockquote")) return "blockquote";
  for (const format of BLOCK_FORMATS) {
    if (format.level > 0 && editor.isActive("heading", { level: format.level })) {
      return format.id;
    }
  }
  return "paragraph";
}

function applyBlockFormat(editor: Editor, id: BlockFormatId): void {
  const chain = editor.chain().focus();
  switch (id) {
    case "blockquote":
      chain.toggleBlockquote().run();
      return;
    case "codeBlock":
      chain.toggleCodeBlock().run();
      return;
    case "paragraph":
      chain.setParagraph().run();
      return;
    default: {
      const level = BLOCK_FORMATS.find((format) => format.id === id)?.level ?? 1;
      chain.setHeading({ level: level as 1 | 2 | 3 | 4 }).run();
    }
  }
}

interface RichTextToolbarProps {
  editor: Editor;
  onInsertImage: () => void;
  imageDisabled: boolean;
  imageTitle: string;
}

export function RichTextToolbar({
  editor,
  onInsertImage,
  imageDisabled,
  imageTitle,
}: RichTextToolbarProps) {
  const { t } = useTranslation();
  const [linkDraft, setLinkDraft] = useState("");

  // React does not re-render on editor transactions (Tiptap v3 dropped that to
  // avoid re-rendering the whole document on every keystroke). Without this
  // subscription every `isActive` below would be frozen at the value it had
  // when the editor mounted — which is exactly why the buttons never lit up.
  const state = useEditorState({
    editor,
    selector: ({ editor }) => ({
      blockFormat: currentBlockFormat(editor),
      bold: editor.isActive("bold"),
      italic: editor.isActive("italic"),
      underline: editor.isActive("underline"),
      strike: editor.isActive("strike"),
      code: editor.isActive("code"),
      bulletList: editor.isActive("bulletList"),
      orderedList: editor.isActive("orderedList"),
      taskList: editor.isActive("taskList"),
      link: editor.isActive("link"),
      linkHref: String(editor.getAttributes("link").href ?? ""),
      inTable: editor.isActive("table"),
      // Indent/outdent act on the item node, and a task item is a different
      // node type than a bullet/ordered one — pass the wrong name and the
      // command silently no-ops.
      listItemType: editor.isActive("taskItem")
        ? "taskItem"
        : editor.isActive("listItem")
          ? "listItem"
          : null,
      align:
        TEXT_ALIGNMENTS.find((alignment) =>
          editor.isActive({ textAlign: alignment }),
        ) ?? "left",
      fontFamily: String(editor.getAttributes("textStyle").fontFamily ?? ""),
      fontSize: String(editor.getAttributes("textStyle").fontSize ?? ""),
      color: String(editor.getAttributes("textStyle").color ?? ""),
      highlight: String(editor.getAttributes("highlight").color ?? ""),
      canUndo: editor.can().undo(),
      canRedo: editor.can().redo(),
    }),
  });

  const fontFamilyId =
    FONT_FAMILIES.find((font) => font.value === state.fontFamily)?.id ?? "custom";

  // Whether any control tucked into the overflow menu is currently engaged —
  // shown on the trigger itself so an applied-but-hidden format is still
  // visible at a glance, the same way the color/highlight/align triggers
  // used to light up on their own.
  const overflowActive =
    state.strike ||
    state.code ||
    state.taskList ||
    state.align !== "left" ||
    Boolean(state.fontFamily) ||
    Boolean(state.fontSize) ||
    Boolean(state.color) ||
    Boolean(state.highlight) ||
    state.inTable;

  function openLinkMenu() {
    setLinkDraft(state.linkHref);
  }

  function applyLink(close: () => void) {
    const href = linkDraft.trim();
    if (!href) {
      editor.chain().focus().unsetLink().run();
    } else {
      editor.chain().focus().extendMarkRange("link").setLink({ href }).run();
    }
    close();
  }

  return (
    <div className="rich-text-toolbar" role="toolbar">
      <ToolbarButton
        icon="undo"
        title={t("richText.undo")}
        disabled={!state.canUndo}
        onClick={() => editor.chain().focus().undo().run()}
      />
      <ToolbarButton
        icon="redo"
        title={t("richText.redo")}
        disabled={!state.canRedo}
        onClick={() => editor.chain().focus().redo().run()}
      />

      <span className="rich-text-toolbar-divider" />

      <ToolbarMenu
        label={t(`richText.format.${state.blockFormat}`)}
        title={t("richText.format.menu")}
        className="wide"
      >
        {(close) =>
          BLOCK_FORMATS.map((format) => (
            <MenuItem
              key={format.id}
              label={
                <span className={`rich-text-format-preview is-${format.id}`}>
                  {t(`richText.format.${format.id}`)}
                </span>
              }
              isActive={state.blockFormat === format.id}
              onClick={() => {
                applyBlockFormat(editor, format.id);
                close();
              }}
            />
          ))
        }
      </ToolbarMenu>

      <span className="rich-text-toolbar-divider" />

      <ToolbarButton
        icon="bold"
        title={t("richText.bold")}
        isActive={state.bold}
        onClick={() => editor.chain().focus().toggleBold().run()}
      />
      <ToolbarButton
        icon="italic"
        title={t("richText.italic")}
        isActive={state.italic}
        onClick={() => editor.chain().focus().toggleItalic().run()}
      />
      <ToolbarButton
        icon="underline"
        title={t("richText.underline")}
        isActive={state.underline}
        onClick={() => editor.chain().focus().toggleUnderline().run()}
      />

      <span className="rich-text-toolbar-divider" />

      <ToolbarButton
        icon="bulletList"
        title={t("richText.bulletList")}
        isActive={state.bulletList}
        onClick={() => editor.chain().focus().toggleBulletList().run()}
      />
      <ToolbarButton
        icon="orderedList"
        title={t("richText.orderedList")}
        isActive={state.orderedList}
        onClick={() => editor.chain().focus().toggleOrderedList().run()}
      />

      <span className="rich-text-toolbar-divider" />

      <ToolbarMenu
        icon="link"
        title={t("richText.link.menu")}
        isActive={state.link}
        className="wide"
      >
        {(close) => (
          <div className="rich-text-link-form" onMouseDown={(e) => e.stopPropagation()}>
            <input
              type="url"
              autoFocus
              placeholder="https://"
              value={linkDraft}
              onFocus={openLinkMenu}
              onChange={(e) => setLinkDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  applyLink(close);
                }
              }}
            />
            <div className="rich-text-link-actions">
              <button type="button" onClick={() => applyLink(close)}>
                {t("richText.link.apply")}
              </button>
              <button
                type="button"
                disabled={!state.link}
                onClick={() => {
                  editor.chain().focus().unsetLink().run();
                  close();
                }}
              >
                {t("richText.link.remove")}
              </button>
            </div>
          </div>
        )}
      </ToolbarMenu>

      <ToolbarButton
        icon="image"
        title={imageTitle}
        disabled={imageDisabled}
        onClick={onInsertImage}
      />

      <span className="rich-text-toolbar-divider" />

      {/* Everything below is reached less often than the controls above —
          grouped here instead of spread across the bar so the toolbar's
          width stops growing with every formatting feature it picks up.
          Items intentionally don't close this menu on click (same as the
          table actions below always did): several are typically applied in
          a row (e.g. font, then size, then colour). */}
      <ToolbarMenu
        icon="more"
        title={t("richText.more.menu")}
        isActive={overflowActive}
        className="wide"
      >
        {() => (
          <>
            <MenuItem
              label={iconLabel("strike", t("richText.strike"))}
              isActive={state.strike}
              onClick={() => editor.chain().focus().toggleStrike().run()}
            />
            <MenuItem
              label={iconLabel("code", t("richText.inlineCode"))}
              isActive={state.code}
              onClick={() => editor.chain().focus().toggleCode().run()}
            />
            <MenuItem
              label={iconLabel("taskList", t("richText.taskList"))}
              isActive={state.taskList}
              onClick={() => editor.chain().focus().toggleTaskList().run()}
            />
            <MenuItem
              label={iconLabel("outdent", t("richText.outdent"))}
              disabled={!state.listItemType}
              onClick={() =>
                editor.chain().focus().liftListItem(state.listItemType ?? "listItem").run()
              }
            />
            <MenuItem
              label={iconLabel("indent", t("richText.indent"))}
              disabled={!state.listItemType}
              onClick={() =>
                editor.chain().focus().sinkListItem(state.listItemType ?? "listItem").run()
              }
            />
            <MenuItem
              label={iconLabel("hr", t("richText.horizontalRule"))}
              onClick={() => editor.chain().focus().setHorizontalRule().run()}
            />
            <MenuItem
              label={iconLabel("clear", t("richText.clearFormatting"))}
              onClick={() => editor.chain().focus().unsetAllMarks().clearNodes().run()}
            />

            <span className="rich-text-menu-separator" />
            <div className="rich-text-menu-caption">{t("richText.align.menu")}</div>
            {TEXT_ALIGNMENTS.map((alignment) => (
              <MenuItem
                key={alignment}
                label={iconLabel(ALIGN_ICONS[alignment], t(`richText.align.${alignment}`))}
                isActive={state.align === alignment}
                onClick={() => editor.chain().focus().setTextAlign(alignment).run()}
              />
            ))}

            <span className="rich-text-menu-separator" />
            <div className="rich-text-menu-caption">{t("richText.font.menu")}</div>
            {FONT_FAMILIES.map((font) => (
              <MenuItem
                key={font.id}
                label={
                  <span style={font.value ? { fontFamily: font.value } : undefined}>
                    {t(`richText.font.${font.id}`)}
                  </span>
                }
                isActive={fontFamilyId === font.id}
                onClick={() => {
                  const chain = editor.chain().focus();
                  if (font.value) chain.setFontFamily(font.value).run();
                  else chain.unsetFontFamily().run();
                }}
              />
            ))}
            <div className="rich-text-menu-caption">{t("richText.font.size")}</div>
            {FONT_SIZES.map((size) => (
              <MenuItem
                key={size}
                label={size}
                isActive={state.fontSize === size}
                onClick={() => editor.chain().focus().setFontSize(size).run()}
              />
            ))}
            <MenuItem
              label={t("richText.font.sizeReset")}
              onClick={() => editor.chain().focus().unsetFontSize().run()}
            />

            <span className="rich-text-menu-separator" />
            <div className="rich-text-menu-caption">{t("richText.textColor")}</div>
            <ColorGrid
              colors={TEXT_COLORS}
              current={state.color}
              resetLabel={t("richText.colorReset")}
              onPick={(color) => editor.chain().focus().setColor(color).run()}
              onReset={() => editor.chain().focus().unsetColor().run()}
            />

            <span className="rich-text-menu-separator" />
            <div className="rich-text-menu-caption">{t("richText.highlight")}</div>
            <ColorGrid
              colors={HIGHLIGHT_COLORS}
              current={state.highlight}
              resetLabel={t("richText.highlightReset")}
              onPick={(color) => editor.chain().focus().setHighlight({ color }).run()}
              onReset={() => editor.chain().focus().unsetHighlight().run()}
            />

            <span className="rich-text-menu-separator" />
            <div className="rich-text-menu-caption">{t("richText.table.menu")}</div>
            <MenuItem
              label={t("richText.table.insert")}
              onClick={() => editor.chain().focus().insertTable(DEFAULT_TABLE).run()}
            />
            <MenuItem
              label={t("richText.table.addRowAfter")}
              disabled={!state.inTable}
              onClick={() => editor.chain().focus().addRowAfter().run()}
            />
            <MenuItem
              label={t("richText.table.addColumnAfter")}
              disabled={!state.inTable}
              onClick={() => editor.chain().focus().addColumnAfter().run()}
            />
            <MenuItem
              label={t("richText.table.deleteRow")}
              disabled={!state.inTable}
              onClick={() => editor.chain().focus().deleteRow().run()}
            />
            <MenuItem
              label={t("richText.table.deleteColumn")}
              disabled={!state.inTable}
              onClick={() => editor.chain().focus().deleteColumn().run()}
            />
            <MenuItem
              label={t("richText.table.toggleHeaderRow")}
              disabled={!state.inTable}
              onClick={() => editor.chain().focus().toggleHeaderRow().run()}
            />
            <MenuItem
              label={t("richText.table.mergeOrSplit")}
              disabled={!state.inTable}
              onClick={() => editor.chain().focus().mergeOrSplit().run()}
            />
            <MenuItem
              label={t("richText.table.delete")}
              disabled={!state.inTable}
              onClick={() => editor.chain().focus().deleteTable().run()}
            />
          </>
        )}
      </ToolbarMenu>
    </div>
  );
}
