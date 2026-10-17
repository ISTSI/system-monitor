import type { components } from './schema';

// API payloads come from the backend's generated OpenAPI document.
export type Bootstrap = components['schemas']['BootstrapResponse'];
export type Preferences = components['schemas']['PreferenceResponse'];
export type ThemeMode = Preferences['theme_mode'];
export type Settings = components['schemas']['SettingsResponse'];
export type Session = components['schemas']['SessionResponse'];
export type Role = Session['role'];
export type CatalogueEntry = components['schemas']['CatalogueEntry'];
export type Viewer = components['schemas']['ProjectViewerResponse'];
export type Subsystem = components['schemas']['DemoSubsystem'];
export type Server = components['schemas']['DemoServer'];
export type Process = components['schemas']['DemoProcess'];
export type Workspace = components['schemas']['WorkspaceResponse'];
export type User = components['schemas']['AccountResponse'];
