using Microsoft.AspNetCore.Mvc;

namespace Jellyfin.Plugin.CutDaCord.Controller;

[ApiController]
[Route("[controller]")]
public class CutDaCordController : ControllerBase
{
    [HttpGet("Config")]
    public ActionResult<object> GetConfig()
    {
        return Ok(new
        {
            apiBaseUrl = CutDaCordPlugin.Instance.Configuration.ApiBaseUrl
        });
    }
}
