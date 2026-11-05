"""Original editorial graphics. No likeness or scraped photography."""
import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from app.core.languages import language_info
from app.video.fonts import resolve_font

def font(size, bold=False):
    for name in (["arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold else ["arial.ttf", "DejaVuSans.ttf"]):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)

def create_demo_slides(topic, personality, script, output_dir: Path, count=5, language='en-US'):
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    labels = ['THE BIG QUESTION', 'KEY CONTEXT', 'THE EVIDENCE', 'DEEPER IMPACT', 'BEYOND THE HEADLINE']
    localized = language_info(language).code != 'en-US'
    if localized:
        labels = [f'{index+1:02} / {count:02}' for index in range(count)]
    subject_font = resolve_font(language, personality).load(68) if localized else font(68, True)
    subject_options = {'direction': 'rtl', 'align': 'right'} if language_info(language).rtl else {}
    colors = ['#61e8b6', '#8faaff', '#ffcc80', '#d6a3ff', '#65d9f5']

    for index in range(count):
        accent = colors[index % len(colors)]
        image = Image.new('RGB', (1080, 1920), '#0c1526')
        draw = ImageDraw.Draw(image)

        # Subtle elegant dark gradient background
        for y in range(1920):
            r = int(12 + (y / 1920) * 10)
            g = int(21 + (y / 1920) * 14)
            b = int(38 + (y / 1920) * 20)
            draw.line((0, y, 1080, y), fill=(r, g, b))

        # Ambient backdrop glow
        draw.ellipse((540 - 320, 480, 540 + 320, 1120), fill='#15253b')

        # Top Section: Channel / Story Header (y: 130-340)
        draw.text((90, 140), 'FRAMEFLOW' if localized else 'FRAMEFLOW / EDITORIAL STORY', font=font(26, True), fill=accent)
        draw.multiline_text((90, 210), textwrap.fill(personality, 20), font=subject_font, fill='white', spacing=8, **subject_options)

        # Upper Context Badge (y: 360-410) - positioned well above the subtitle zone
        badge_text = labels[index % len(labels)]
        badge_w = int(len(badge_text) * 17 + 50)
        draw.rounded_rectangle((90, 360, 90 + badge_w, 416), radius=16, fill=accent)
        draw.text((115, 375), badge_text, font=font(22, True), fill='#0c1526')

        # Middle Area: Distinct Intentional Editorial Card per scene (y: 460 - 1260)
        card_box = (90, 460, 990, 1260)
        draw.rounded_rectangle(card_box, radius=28, fill='#111f33', outline='#243a56', width=3)

        scene_type = index % 5
        if scene_type == 0:
            # Hook / Spotlight Card: Concentric focal rings + Key Question Iconography
            draw.ellipse((440, 560, 640, 760), fill='#182d47', outline=accent, width=4)
            draw.ellipse((480, 600, 600, 720), fill=accent)
            draw.text((524, 620), '?', font=font(82, True), fill='#0c1526')
            draw.text((150, 840), 'KEY QUESTION', font=font(34, True), fill=accent)
            prompt_text = textwrap.fill(topic or personality, 28)
            draw.multiline_text((150, 910), prompt_text[:140], font=font(40, True), fill='#f0f4f8', spacing=14)

        elif scene_type == 1:
            # Context & Fact Metric Card: Dual-panel infographic
            draw.text((150, 520), 'BACKGROUND & CONTEXT', font=font(30, True), fill=accent)
            # Panel 1
            draw.rounded_rectangle((140, 590, 940, 870), radius=20, fill='#172a42', outline='#2a4463', width=2)
            draw.text((180, 630), 'REPORTED DEVELOPMENT', font=font(24, True), fill=accent)
            detail = textwrap.fill((topic or personality), 34)
            draw.multiline_text((180, 680), detail[:160], font=font(32), fill='#ffffff', spacing=10)
            # Panel 2: Verified Source Marker
            draw.rounded_rectangle((140, 910, 940, 1180), radius=20, fill='#172a42', outline='#2a4463', width=2)
            draw.text((180, 950), 'SOURCE EVALUATION', font=font(24, True), fill='#8faaff')
            draw.multiline_text((180, 1000), 'Independent corroboration and primary\nevidence assessed for factual grounding.', font=font(30), fill='#d0dbe8', spacing=10)

        elif scene_type == 2:
            # Quote / Focus Card: Stylized editorial blockquote
            draw.text((140, 500), '“', font=font(140, True), fill=accent)
            snippet = (script[:180] if script else 'Direct factual evidence examined in full context.')
            quote_text = textwrap.fill(snippet, 26)
            draw.multiline_text((160, 640), quote_text[:190], font=font(42, True), fill='#ffffff', spacing=16)
            draw.rounded_rectangle((160, 1120, 480, 1180), radius=14, fill='#1b304c')
            draw.text((185, 1135), 'VERIFIED CLAIM', font=font(24, True), fill=accent)

        elif scene_type == 3:
            # Analysis / Breakdown Card: Stepped progression
            draw.text((150, 520), 'ANALYSIS & IMPLICATIONS', font=font(30, True), fill=accent)
            steps = ['Material claim identified', 'Corroboration reviewed', 'Wider significance established']
            for s_idx, s_text in enumerate(steps):
                y_step = 610 + s_idx * 190
                draw.rounded_rectangle((140, y_step, 940, y_step + 145), radius=18, fill='#172a42')
                draw.rounded_rectangle((170, y_step + 35, 240, y_step + 105), radius=12, fill=accent)
                draw.text((192, y_step + 45), str(s_idx + 1), font=font(36, True), fill='#0c1526')
                draw.text((270, y_step + 52), s_text, font=font(32, True), fill='#f0f4f8')

        else:
            # Summary / Takeaway Card
            draw.text((150, 530), 'THE BIG TAKEAWAY', font=font(34, True), fill=accent)
            draw.line((150, 590, 450, 590), fill=accent, width=3)
            sum_text = textwrap.fill(topic or personality, 28)
            draw.multiline_text((150, 650), sum_text[:160], font=font(40, True), fill='#ffffff', spacing=14)
            draw.rounded_rectangle((140, 980, 940, 1180), radius=20, fill='#172a42', outline=accent, width=2)
            draw.text((180, 1020), 'NEXT STEPS TO FOLLOW', font=font(24, True), fill=accent)
            draw.text((180, 1075), 'Ongoing reporting and verified updates.', font=font(30), fill='#d0dbe8')

        # Subtitle Safe Zone: y = 1320 to 1680 is left completely CLEAR of cards/badges!

        # Footer: y = 1760 (Attribution / Archival disclaimer)
        if not localized:
            draw.text((90, 1760), 'ORIGINAL EDITORIAL GRAPHIC  •  INFORMATIONAL CARD', font=font(24), fill='#6b8199')

        path = output_dir / f'slide_{index+1}.jpg'
        image.save(path, quality=94)
        paths.append(path)

    return paths

