"""Actual OS service startup, crash recovery, stop/start and removal."""
import json,os,pathlib,subprocess,sys,tempfile,time,uuid
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import deploy

area=pathlib.Path.home()/'.cache/ziokt-daemon-acceptance';area.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='ziokt-daemon-',dir=area) as temporary:
 root=pathlib.Path(temporary);name='ziokt-ci-'+uuid.uuid4().hex[:10]
 worker=root/'worker.py';state=root/'heartbeat.json'
 worker.write_text('''import json,os,pathlib,sys,time
p=pathlib.Path(sys.argv[1]);first=not p.with_suffix('.crashed').exists()
for i in range(12000):
 q=p.with_suffix('.next');q.write_text(json.dumps({'pid':os.getpid(),'at':time.time()}));q.replace(p)
 if first and i==20:p.with_suffix('.crashed').write_text('actual exit 7');raise SystemExit(7)
 time.sleep(.1)
''')
 definition=None
 def wait(predicate,timeout=110):
  end=time.monotonic()+timeout
  while time.monotonic()<end:
   try:
    if state.exists():
     value=json.loads(state.read_text())
     if predicate(value):return value
   except (OSError,ValueError):pass
   time.sleep(.2)
  raise TimeoutError('actual OS daemon failed its lifecycle assertion')
 try:
  definition=deploy.persist(root,'ci-probe',[sys.executable,str(worker),str(state)],name=name)
  deploy.write(root/'services.json',{name:{'service':name,'definition':definition}})
  first=wait(lambda value:time.time()-value['at']<2,30)
  second=wait(lambda value:value['pid']!=first['pid'] and time.time()-value['at']<2)
  deploy.service_control(root,'stop',name);time.sleep(2);stopped=json.loads(state.read_text())['at'];time.sleep(2)
  assert json.loads(state.read_text())['at']==stopped,'stop left a child process running'
  deploy.service_control(root,'start',name)
  third=wait(lambda value:value['pid']!=second['pid'] and time.time()-value['at']<2,30)
  deploy.service_control(root,'restart',name)
  fourth=wait(lambda value:value['pid']!=third['pid'] and time.time()-value['at']<2,35)
  print(json.dumps({'schema':'ziokt.daemon-lifecycle.v1','platform':sys.platform,'actual_os_backend':True,'startup':True,'crash_restarted':True,'stop_terminated_child':True,'start':True,'restart':True,'status':'PASS'}))
 finally:
  if definition:deploy.service_control(root,'uninstall',name)
