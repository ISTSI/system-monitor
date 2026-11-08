import { useRef, useState } from 'react';
import { useI18n } from '../i18n';
import { helpChapters, helpText, matchingHelpChapters } from '../helpContent';
import { Modal } from './Common';
import './help.css';

export default function HelpDialog({ onClose }: { onClose: () => void }) {
  const { language, t } = useI18n();
  const [chapterId, setChapterId] = useState(helpChapters[0].id);
  const [query, setQuery] = useState('');
  const article = useRef<HTMLElement>(null);
  const matches = matchingHelpChapters(query, language);
  const chapter = matches.find(item => item.id === chapterId) ?? matches[0];
  return <Modal title={t('Help')} className="help-dialog" onClose={onClose}>
    <p className="help-intro">{t('Bundled guide · available offline · opening Help preserves this page’s investigation and monitor.')}</p>
    <label className="help-search">{t('Search Help')}<input type="search" value={query} onChange={event => { setQuery(event.target.value); if (article.current) article.current.scrollTop = 0; }} placeholder={t('Find a topic or an operation…')} /></label>
    <div className="help-layout">
      <nav className="help-chapters" aria-label={t('Help chapters')}>
        {matches.map(item => <button key={item.id} type="button" title={helpText(item.title, language)} aria-current={chapter?.id === item.id ? 'page' : undefined} onClick={() => { setChapterId(item.id); if (article.current) article.current.scrollTop = 0; article.current?.focus(); }}>{helpText(item.title, language)}</button>)}
      </nav>
      <article ref={article} className="help-article" tabIndex={0} aria-label={t('Help chapter content')}>
        {chapter ? <><h3>{helpText(chapter.title, language)}</h3>{chapter.sections.map((section, index) => <section key={index}>
          <h4>{helpText(section.title, language)}</h4>
          {section.paragraphs.map((paragraph, paragraphIndex) => <p key={paragraphIndex}>{helpText(paragraph, language)}</p>)}
          {section.operations && <dl className="help-operations">{section.operations.map(operation => <div key={operation.name}><dt><code>{operation.name}</code></dt><dd>{helpText(operation.description, language)}</dd></div>)}</dl>}
        </section>)}</> : <p role="status">{t('No Help chapters match. Try another term.')}</p>}
      </article>
    </div>
  </Modal>;
}
