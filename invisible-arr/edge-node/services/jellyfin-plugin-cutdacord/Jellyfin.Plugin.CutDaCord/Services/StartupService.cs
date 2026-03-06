using System.Reflection;
using System.Runtime.Loader;
using Jellyfin.Plugin.CutDaCord.Helpers;
using MediaBrowser.Model.Tasks;
using Microsoft.Extensions.Logging;
using Newtonsoft.Json.Linq;

namespace Jellyfin.Plugin.CutDaCord.Services;

public class StartupService : IScheduledTask
{
    public string Name => "CutDaCord Startup";
    public string Key => "Jellyfin.Plugin.CutDaCord.Startup";
    public string Description => "Registers CutDaCord file transformations for JS/CSS injection.";
    public string Category => "Startup Services";

    private readonly ILogger<CutDaCordPlugin> _logger;

    public StartupService(ILogger<CutDaCordPlugin> logger)
    {
        _logger = logger;
    }

    public Task ExecuteAsync(IProgress<double> progress, CancellationToken cancellationToken)
    {
        _logger.LogInformation("CutDaCord: Registering file transformations.");

        var payload = new JObject
        {
            ["id"] = "b2c3d4e5-f6a7-8901-bcde-f12345678901",
            ["fileNamePattern"] = "index.html",
            ["callbackAssembly"] = GetType().Assembly.FullName,
            ["callbackClass"] = typeof(TransformationPatches).FullName,
            ["callbackMethod"] = nameof(TransformationPatches.IndexHtml)
        };

        Assembly? ftAssembly = AssemblyLoadContext.All
            .SelectMany(x => x.Assemblies)
            .FirstOrDefault(x => x.FullName?.Contains(".FileTransformation") ?? false);

        if (ftAssembly != null)
        {
            Type? pluginInterface = ftAssembly.GetType(
                "Jellyfin.Plugin.FileTransformation.PluginInterface");

            if (pluginInterface != null)
            {
                pluginInterface.GetMethod("RegisterTransformation")
                    ?.Invoke(null, new object?[] { payload });
                _logger.LogInformation("CutDaCord: File transformation registered successfully.");
            }
            else
            {
                _logger.LogWarning("CutDaCord: File Transformation PluginInterface type not found.");
            }
        }
        else
        {
            _logger.LogError("CutDaCord: File Transformation plugin not found! " +
                "Install it from: https://github.com/IAmParadox27/jellyfin-plugin-file-transformation");
        }

        return Task.CompletedTask;
    }

    public IEnumerable<TaskTriggerInfo> GetDefaultTriggers() => StartupServiceHelper.GetDefaultTriggers();
}
