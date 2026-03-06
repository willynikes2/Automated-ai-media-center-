#!/bin/bash
cd /home/shawn/Automated-ai-media-center-/invisible-arr/edge-node
python3 scripts/build_epg_from_xtream.py config/iptv/kemo_filtered.m3u config/iptv/epg.xml 2>&1 | tail -5
# Flush EPG cache so gateway picks up new file
docker exec redis redis-cli -a d95605b5d14488d5af21eb23b0435731 DEL $(docker exec redis redis-cli -a d95605b5d14488d5af21eb23b0435731 KEYS "iptv:epg:*" 2>/dev/null | tr '\n' ' ') 2>/dev/null || true
echo "[$(date)] EPG refresh complete"
