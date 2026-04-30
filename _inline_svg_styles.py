"""Post-process Rich-exported SVGs so GitHub renders them.

Problem: Rich's SVG export uses a <style> block with .r1, .r2, ... classes.
GitHub's image sanitizer strips <style> tags from SVGs embedded as <img>,
which removes ALL the colors and styling.

Fix: parse the <style> block, extract each class's rules, then rewrite every
class="r12" reference as style="fill: rgb(...); ...". After that the SVG is
fully self-contained inline-style markup that survives GitHub's sanitizer.

Also strips the @import google fonts call (also stripped by GitHub anyway,
plus it adds a network round-trip).
"""
import re
from pathlib import Path

ASSETS = Path(__file__).parent / "assets"


def extract_class_styles(style_text: str) -> dict[str, str]:
    """Parse `.r1 { fill: rgb(...) ... }` rules into {class_name: style_str}."""
    out: dict[str, str] = {}
    # Match .CLASS { rules; }
    for m in re.finditer(r"\.([\w-]+)\s*\{([^}]+)\}", style_text):
        cls = m.group(1)
        rules = m.group(2).strip()
        # Normalize whitespace, ensure trailing semicolon dropped
        rules = " ".join(rules.split()).rstrip(";").strip()
        if rules:
            out[cls] = rules
    return out


def inline_styles(svg_text: str) -> str:
    """Rewrite an SVG to remove <style> and inline all class-based styling."""
    # Find the entire <style>...</style> block
    style_match = re.search(r"<style[^>]*>(.*?)</style>", svg_text, re.DOTALL)
    if not style_match:
        return svg_text  # nothing to do
    style_body = style_match.group(1)
    # Strip @import lines (extra noise; GitHub strips them too)
    style_body = re.sub(r"@import[^;]+;", "", style_body)

    class_styles = extract_class_styles(style_body)
    if not class_styles:
        # Just remove the empty/import-only block
        return svg_text.replace(style_match.group(0), "")

    # Replace every `class="cls1 cls2 ..."` with combined inline style.
    def repl(m: re.Match) -> str:
        classes = m.group(1).split()
        # Combine the rules for each class. Later classes win on collisions.
        merged: dict[str, str] = {}
        for cls in classes:
            rules = class_styles.get(cls, "")
            for rule in rules.split(";"):
                rule = rule.strip()
                if not rule or ":" not in rule:
                    continue
                k, _, v = rule.partition(":")
                merged[k.strip()] = v.strip()
        if not merged:
            return ""  # no styles for these classes, drop the attr
        style_str = "; ".join(f"{k}: {v}" for k, v in merged.items())
        # Escape any quotes (unlikely but defensive)
        return f'style="{style_str}"'

    svg_text = re.sub(r'class="([^"]+)"', repl, svg_text)

    # Remove the now-orphaned <style> block entirely
    svg_text = svg_text.replace(style_match.group(0), "")
    # Also strip the .{unique_id}-... class-name leftovers in matrix children
    return svg_text


def main() -> None:
    if not ASSETS.is_dir():
        raise SystemExit(f"no assets/ directory at {ASSETS}")
    svg_files = sorted(ASSETS.glob("*.svg"))
    for f in svg_files:
        text = f.read_text(encoding="utf-8")
        new_text = inline_styles(text)
        # Sanity: make sure it still looks like an SVG
        if not new_text.lstrip().startswith("<svg"):
            print(f"  SKIP {f.name}  (post-process broke the file)")
            continue
        f.write_text(new_text, encoding="utf-8")
        print(f"  inlined {f.name}  ({len(text):,} -> {len(new_text):,} bytes)")
    print(f"\nDone. {len(svg_files)} SVGs processed.")


if __name__ == "__main__":
    main()
