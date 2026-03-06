using MediaBrowser.Model.Plugins;

namespace Jellyfin.Plugin.CutDaCord.Configuration;

public class PluginConfiguration : BasePluginConfiguration
{
    public string ApiBaseUrl { get; set; } = "https://api.cutdacord.app";
}
