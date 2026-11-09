"""Non-destructive inspection. Does not start/stop/recreate machines or containers."""
from pathlib import Path
import subprocess,json,hashlib,datetime,stat,os,urllib.request
ROOT=Path(__file__).resolve().parents[2]
P='/Users/haochenglin/.local/podman/bin/podman'
def run(args):
 p=subprocess.run(args,text=True,capture_output=True,timeout=40)
 return {'command':args,'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
def jp(args):return json.loads(subprocess.check_output([P]+args,text=True,timeout=20))
c=jp(['inspect','riskscope'])[0];cfg=c['Config'];host=c['HostConfig']
out={'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'version':jp(['version','--format','json']), 'machine':jp(['machine','inspect','riskscope-machine']),
 'machine_list':jp(['machine','list','--format','json']), 'provider_default':jp(['machine','info','--format','json']),
 'provider_applehv':None, # default-provider metadata recorded without changing configuration
 'container':{'id':c['Id'],'image':c['Image'],'user':cfg['User'],'command':cfg['Cmd'],
   'env':[e for e in cfg['Env'] if e.startswith(('OLLAMA_','AGENT_'))],
   'privileged':host['Privileged'],'restart':host['RestartPolicy'],'autoremove':host.get('AutoRemove'),
   'ports':host['PortBindings'],'mounts':c['Mounts'],'healthcheck':cfg.get('Healthcheck'),'status':c['State']['Status']},
 'volume':jp(['volume','inspect','riskscope_runtime']),
 'stats':jp(['stats','--no-stream','--format','json']),
 'listeners':run(['lsof','-nP','-iTCP:8000','-iTCP:11434','-sTCP:LISTEN']),
 'interactive_path':run(['zsh','-ic','command -v podman; podman --version']),
 'installed_files':[], 'host_resources':run(['sysctl','-n','hw.memsize','hw.logicalcpu'])}
for p in Path('/Users/haochenglin/.local/podman/bin').iterdir():
 s=p.stat();out['installed_files'].append({'name':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'mode':oct(stat.S_IMODE(s.st_mode)),'uid':s.st_uid,'gid':s.st_gid,'size':s.st_size,'signature':run(['codesign','--verify','--strict','--verbose=2',str(p)])})
app='/Applications/Podman Desktop.app';pkg=app+'/Contents/Resources/extensions/podman/packages/extension/assets/podman-installer-macos-aarch64-v6.1.4.pkg'
out['package_signature']=run(['pkgutil','--check-signature',pkg]);out['desktop_signer']=run(['codesign','-dv','--verbose=4',app]);out['desktop_gatekeeper']=run(['spctl','--assess','--type','execute','--verbose=2',app])
out['health']=json.load(urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=5))
# Only read source hashes, credential file permissions and aggregate DB counts.
code="""from pathlib import Path
import hashlib,json,urllib.request,sqlite3,stat,os
files=[str(p.relative_to('/app')) for p in Path('/app/app').rglob('*') if p.is_file() and p.suffix in ('.py','.js','.html')]
o={'source_hashes':{p:hashlib.sha256(Path('/app',p).read_bytes()).hexdigest() for p in files}}
c=sqlite3.connect('file:/app/runtime/agent.sqlite3?mode=ro',uri=True);c.execute('PRAGMA query_only=ON')
o['counts']={t:c.execute('select count(*) from '+t).fetchone()[0] for t in ['users','sessions','analyses','facts','actions','audit']};c.close()
o['credential_mode']=oct(stat.S_IMODE(Path('/app/runtime/demo_credentials.json').stat().st_mode));o['uid']=os.getuid()
r=urllib.request.urlopen('http://host.containers.internal:11434/api/tags',timeout=5)
o['ollama_status']=r.status;o['qwen3_8b_present']=any(x.get('name')=='qwen3:8b' for x in json.load(r)['models'])
print(json.dumps(o))"""
inside=json.loads(subprocess.check_output([P,'exec','riskscope','python','-B','-c',code],text=True,timeout=20));out['container_read_probe']=inside
out['host_source_hashes']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inside['source_hashes'] if (ROOT/p).exists()}
out['source_mismatches']=[p for p,h in inside['source_hashes'].items() if out['host_source_hashes'].get(p)!=h]
Path(__file__).with_name('inspection.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':out['container']['status'],'source_mismatches':out['source_mismatches'],'container_read_probe':{k:v for k,v in inside.items() if k!='source_hashes'},'evidence':'inspection.json'},indent=2))
