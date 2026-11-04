"""Explicit quote mappings, kept separate from the 175 LLM draft facts."""
import hashlib
from collect_additions import ROOT, read, save, register, manifest

MAPPING = {
 'portugaldom': [
  ('consultation', 'Консультация 60 минут', None),
  ('nif', 'NIF (налоговый номер)', None),
  ('niss', 'NISS (номер социального страхования)', None),
  ('assistance', 'Для одного человека Полное сопровождение при получении ВНЖ в Португалии «под ключ». Подача из любой страны 2500 € за одного человека', 2500),
  ('digital_nomad', 'Виза цифрового кочевника (Digital Nomad / D8)', None)],
 'movetocascais': [
  ('consultation', 'Мы проводим подробные консультации, чтобы понять ваши потребности и ожидания от переезда.', None),
  ('nif', 'От налоговых номеров NIF до полного пакета документов на проживание', None),
  ('assistance', 'Мы оказываем всестороннюю поддержку иностранным гражданам, желающим иммигрировать в эту страну или приехать на определенный срок.', None),
  ('digital_nomad', 'Highly Qualified visa (D3) Passive Income Visa (D7) Digital Nomad Visa Startup Visa', None)],
 'monolite': [
  ('nif', 'Оформление номера налогоплательщика NIF', None),
  ('niss', 'Оформление номера социального страхования NISS', None),
  ('company_registration', 'Регистрация ИП или компании', None),
  ('renewal', 'Продление ВНЖ Сопровождение адвоката в AIMA', None),
  ('digital_nomad', 'Виза D8. Digital Nomad', None)],
 'okno': [
  ('company_registration', 'D2, Startup Visa, самостоятельная деятельность, регистрация компании и юридическая поддержка бизнеса.', None),
  ('digital_nomad', 'D8 для удалённой работы на иностранного работодателя или клиентов.', None),
  ('legal_services', 'Иммиграция, ВНЖ и юридическая помощь в Португалии', None)]}


def build():
    register()
    sources = read(ROOT/'input/additions/sources.json')
    chunks, facts = [], []
    criteria = read(ROOT/'input/criteria.json')
    for key, label in [('niss', 'Оформление NISS'), ('digital_nomad', 'Digital Nomad / D8'),
                       ('legal_services', 'Юридическая помощь при иммиграции')]:
        if not any(c['id'] == key for c in criteria):
            criteria.append({'id': key, 'name': label, 'country': 'Portugal', 'fact_ids': {},
                'comparison_note': 'Упоминание на выбранной странице; состав, условия и цена не сопоставлены. Отсутствие записи не означает отсутствия услуги.',
                'mapping_origin': 'explicit_researcher_source_mapping'})
    for source in sources:
        if source['status'] != 'ok': continue
        cid = source['company_id']
        text = (ROOT/'input'/source['text_path']).read_text(encoding='utf-8')
        chunk_id = source['source_id']+'_full'
        chunks.append({'chunk_id': chunk_id, 'source_id': source['source_id'], 'company_id': cid,
                       'start': 0, 'end': len(text), 'text': text})
        for criterion, quote, amount in MAPPING[cid]:
            if quote not in text: raise ValueError('Source changed; review: '+cid+'/'+criterion)
            fid = hashlib.sha256((source['source_id']+criterion+quote).encode()).hexdigest()[:20]
            facts.append({'fact_id': fid, 'company_id': cid, 'source_id': source['source_id'],
                'chunk_id': chunk_id, 'field': 'price' if amount is not None else 'service',
                'value': quote, 'evidence': quote, 'evidence_start': text.index(quote),
                'country': 'Portugal', 'url': source['final_url'], 'amount': amount,
                'currency': 'EUR' if amount is not None else None,
                'price_basis': 'one_applicant_package' if amount else 'not_observed',
                'criterion_id': criterion, 'review_status': 'researcher_mapped_source_claim',
                'origin': {'method': 'explicit_researcher_quote_mapping', 'llm_called': False},
                'semantic_review': 'limited_mapping_not_full_offer_verification'})
            next(c for c in criteria if c['id'] == criterion)['fact_ids'][cid] = [fid]
    save(ROOT/'input/additions/facts.json', {'facts': facts})
    save(ROOT/'input/additions/chunks.json', chunks)
    save(ROOT/'input/criteria.json', criteria)
    manifest()
    print('Mapped', len(facts), 'observations from', len(sources), 'sources')


if __name__ == '__main__': build()
