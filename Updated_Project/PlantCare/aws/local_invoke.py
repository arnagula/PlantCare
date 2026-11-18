import json,time
from plantcare.storage import MemoryStore
from plantcare.service import Service
from plantcare.profile import default
from tools.scenarios import packet
if __name__=='__main__':
    now=time.time();app=Service(MemoryStore(),lambda *args:None,default('simulated'))
    app.handle('telemetry',packet(now,1),now)
    print(json.dumps(app.get_state(now),indent=2))
