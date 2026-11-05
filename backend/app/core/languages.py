"""Single catalog for output languages, typography and provider locale aliases."""
from dataclasses import asdict, dataclass
from fastapi import HTTPException
import re


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    rtl: bool = False
    font_files: tuple = ('arial.ttf', 'DejaVuSans.ttf', 'NotoSans-Regular.ttf')
    google_locales: tuple = ()
    local_aliases: tuple = ()
    @property
    def locale(self):
        return self.code
    def public(self):
        return {'code':self.code,'name':self.name,'locale':self.locale,'rtl':self.rtl,
                'subtitle_font_candidates':list(self.font_files)}


LANGUAGES = {item.code:item for item in (
    Language('en-US','English',local_aliases=('english','en-us','en-gb','en')),
    Language('ur-PK','Urdu',True,('NotoNastaliqUrdu-Regular.ttf','tahoma.ttf','arial.ttf'),('ur-PK','ur-IN'),('urdu','ur-pk','ur-in','ur')),
    Language('es-ES','Spanish',local_aliases=('spanish','es-es','es-mx','es')),
    Language('it-IT','Italian',local_aliases=('italian','it-it','it')),
    Language('zh-CN','Chinese',False,('msyh.ttc','NotoSansCJKsc-Regular.otf','NotoSansSC-Regular.ttf'),('cmn-CN','zh-CN'),('chinese','mandarin','zh-cn','cmn-cn','zh')),
    Language('ar-SA','Arabic',True,('NotoNaskhArabic-Regular.ttf','tahoma.ttf','arial.ttf'),(),('arabic','ar-sa','ar')),
    Language('fr-FR','French',local_aliases=('french','fr-fr','fr')),
    Language('de-DE','German',local_aliases=('german','de-de','de')),
    Language('hi-IN','Hindi',False,('Nirmala.ttc','NotoSansDevanagari-Regular.ttf'),(),('hindi','hi-in','hi')),
    Language('pt-BR','Portuguese',local_aliases=('portuguese','pt-br','pt')),
)}
ALIASES = {code.split('-')[0]:code for code in LANGUAGES}


def language_info(code=None):
    code = 'en-US' if code is None else code
    code = ALIASES.get(code,code)  # Day 1 clients and data remain compatible.
    if code not in LANGUAGES:
        raise HTTPException(400, 'Unsupported language. Supported codes: '+', '.join(LANGUAGES))
    return LANGUAGES[code]


def language_instruction(code):
    language=language_info(code)
    return (f'Write all audience-facing text in natural native {language.name} ({language.code}), '
            'not a word-for-word translation of English. Research may be in any language. '
            'Preserve factual values, names, scores, dates, teams, quotes and locations exactly in meaning. '
            'Use normal target-language renderings of proper nouns when appropriate; never invent or alter facts. '
            'Do not add English explanations or romanize Urdu, Arabic, Hindi or Chinese.')


def text_units(text,code='en-US'):
    return re.findall(r'[\u3400-\u9fff]|[A-Za-z0-9]+|[^\s]',text) if language_info(code).code=='zh-CN' else text.split()


def script_length_instruction(code,duration):
    if language_info(code).code=='zh-CN':
        return f'Target {duration} seconds: approximately {round(duration*3.2)}–{round(duration*4)} spoken Chinese characters total across all five sections. Keep every section concise.'
    return f'Target {duration} seconds: approximately {round(duration*2.2)} spoken words total across all five sections.'
