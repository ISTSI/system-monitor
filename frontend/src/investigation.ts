import type { components } from './api/schema';

export type HistoricalQuery = components['schemas']['HistoricalQueryInput'];
export type HistoricalEvent = components['schemas']['HistoricalEvent'];
export type HistoricalResults = components['schemas']['HistoricalQueryResponse'];
export type HistoricalContext = components['schemas']['HistoricalContextResponse'];
export type InvestigationWorkspace = components['schemas']['SavedWorkspaceResponse'];
export type Bookmark = components['schemas']['BookmarkItem'];
export type Bookmarks = components['schemas']['BookmarkResponse'];
export type Trace = components['schemas']['CorrelationResponse'];
export type BundlePreview = components['schemas']['BundlePreviewResponse'];
export type OfflineInvestigation = components['schemas']['OfflineResponse'];
