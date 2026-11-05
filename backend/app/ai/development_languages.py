"""Explicitly labelled native-language development copy, never factual news."""
COPY = {
 'en-US': ('This is a development example.', 'Check the original source and the date. A headline alone is not evidence.', 'Context matters', '#Context'),
 'ur-PK': ('یہ ترقیاتی جانچ کی ایک مثال ہے۔', 'اصل ماخذ اور تاریخ کی جانچ کریں۔ صرف سرخی کسی دعوے کا ثبوت نہیں ہوتی۔', 'خبر کا پس منظر', '#معلومات'),
 'es-ES': ('Este es un ejemplo de desarrollo.', 'Comprueba la fuente original y la fecha. Un titular por sí solo no demuestra una afirmación.', 'El contexto importa', '#Contexto'),
 'it-IT': ('Questo è un esempio di sviluppo.', 'Controlla la fonte originale e la data. Un titolo da solo non dimostra un fatto.', 'Il contesto conta', '#Contesto'),
 'zh-CN': ('这是开发测试示例。', '请核查原始来源和日期。仅凭标题不能证明某个说法。', '了解新闻背景', '#新闻背景'),
 'ar-SA': ('هذا مثال للاختبار أثناء التطوير.', 'تحقق من المصدر الأصلي والتاريخ. العنوان وحده ليس دليلاً على صحة الادعاء.', 'السياق مهم', '#معلومات'),
 'fr-FR': ('Ceci est un exemple de développement.', 'Vérifiez la source originale et la date. Un titre ne prouve pas une affirmation.', 'Le contexte compte', '#Contexte'),
 'de-DE': ('Dies ist ein Entwicklungsbeispiel.', 'Prüfe die Originalquelle und das Datum. Eine Schlagzeile allein ist kein Beweis.', 'Der Kontext zählt', '#Kontext'),
 'hi-IN': ('यह विकास परीक्षण का एक उदाहरण है।', 'मूल स्रोत और तारीख की जाँच करें। केवल शीर्षक किसी दावे का प्रमाण नहीं है।', 'खबर का संदर्भ', '#जानकारी'),
 'pt-BR': ('Este é um exemplo de desenvolvimento.', 'Confira a fonte original e a data. Uma manchete sozinha não comprova uma afirmação.', 'O contexto importa', '#Contexto'),
}


def development_script(code,personality):
    example,body,cover,_=COPY[code]
    return dict(zip(('hook','context','main_story','why_it_matters','ending'),
                    (personality,example,body,body,cover)))


def development_seo(code,personality,script):
    example,body,cover,tag=COPY[code]
    return {'title':f'{personality}: {cover}'[:95],
            'description':script.get('context',example)+'\n\n'+script.get('why_it_matters',body),
            'hashtags':['#Shorts',tag,'#'+''.join(personality.split())],
            'keywords':[personality,cover,body[:90]],'cover_text':cover}
