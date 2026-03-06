using System.Reflection;
using System.Text.RegularExpressions;
using Jellyfin.Plugin.CutDaCord.Model;

namespace Jellyfin.Plugin.CutDaCord.Helpers;

public static class TransformationPatches
{
    public static string IndexHtml(PatchRequestPayload payload)
    {
        string ns = typeof(CutDaCordPlugin).Namespace!;

        // Load embedded CSS
        using Stream cssStream = Assembly.GetExecutingAssembly()
            .GetManifestResourceStream($"{ns}.Inject.cutdacord.css")!;
        using StreamReader cssReader = new(cssStream);
        string css = cssReader.ReadToEnd();

        // Load embedded JS
        using Stream jsStream = Assembly.GetExecutingAssembly()
            .GetManifestResourceStream($"{ns}.Inject.cutdacord.js")!;
        using StreamReader jsReader = new(jsStream);
        string js = jsReader.ReadToEnd();

        // Inject the API base URL from plugin config
        string apiBaseUrl = CutDaCordPlugin.Instance.Configuration.ApiBaseUrl.TrimEnd('/');
        string configScript = $"window.__CUTDACORD_API__ = '{apiBaseUrl}';";

        // Insert before </body>
        string injection = $"<style>{css}</style><script>{configScript}</script><script defer>{js}</script>";
        string result = Regex.Replace(payload.Contents!, "(</body>)", $"{injection}$1");

        return result;
    }
}
