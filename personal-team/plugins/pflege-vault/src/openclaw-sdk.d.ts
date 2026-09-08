declare module "openclaw/plugin-sdk/plugin-entry" {
  export interface OpenClawPluginToolContext {
    agentId?: string;
    workspaceDir?: string;
  }

  export interface OpenClawPluginApi {
    pluginConfig: unknown;
    registerTool(
      factory: (context: OpenClawPluginToolContext) => unknown,
      options: { name?: string; names?: string[]; optional?: boolean },
    ): void;
  }

  export function definePluginEntry<T>(entry: T): T;
}
