using MediaBrowser.Model.Tasks;

namespace Jellyfin.Plugin.CutDaCord.Services;

public static class StartupServiceHelper
{
    public static IEnumerable<TaskTriggerInfo> GetDefaultTriggers()
    {
        yield return new TaskTriggerInfo()
        {
            Type = TaskTriggerInfoType.StartupTrigger
        };
    }
}
