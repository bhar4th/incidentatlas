import argparse
import json
from pathlib import Path
from .engine import analyze,STRATEGIES
from .evaluate import evaluate,get_scenario,write_demo_results


def main():
    parser=argparse.ArgumentParser(prog='incidentatlas',description='Evidence-first incident investigation')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('serve');p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8100);p.add_argument('--db',default='.incidentatlas/state.sqlite3');p.add_argument('--web-root');p.add_argument('--fastapi',action='store_true')
    p=sub.add_parser('analyze');g=p.add_mutually_exclusive_group(required=True);g.add_argument('--scenario');g.add_argument('--input');p.add_argument('--strategy',choices=STRATEGIES,default='balanced');p.add_argument('--start');p.add_argument('--end');p.add_argument('--output')
    p=sub.add_parser('evaluate');p.add_argument('--strategy',choices=STRATEGIES,default='balanced');p.add_argument('--output')
    sub.add_parser('demo-results')
    p=sub.add_parser('benchmark');p.add_argument('--size',type=int,default=10000);p.add_argument('--repeats',type=int,default=20);p.add_argument('--output')
    args=parser.parse_args()
    if args.command=='serve':
        if args.fastapi:
            try:
                import uvicorn
                from .api import create_app
            except ImportError as exc: parser.error('FastAPI transport requires pip install -r requirements.txt')
            uvicorn.run(create_app(args.db,args.web_root),host=args.host,port=args.port)
        else:
            from .server import serve
            serve(args.host,args.port,args.db,args.web_root)
        return
    if args.command=='analyze':
        events=get_scenario(args.scenario)['events'] if args.scenario else json.loads(Path(args.input).read_text())
        if isinstance(events,dict) and 'events' in events: events=events['events']
        result=analyze(events,args.strategy,args.start,args.end)
    elif args.command=='evaluate': result=evaluate(args.strategy)
    elif args.command=='benchmark':
        from .benchmark import benchmark
        result=benchmark(args.size,args.repeats)
    else:
        write_demo_results();print('Wrote fixtures/demo-results.json');return
    encoded=json.dumps(result,indent=2,allow_nan=False)+'\n'
    if args.output:
        Path(args.output).parent.mkdir(parents=True,exist_ok=True);Path(args.output).write_text(encoded)
        print(f'Wrote {args.output}')
    else: print(encoded,end='')

if __name__=='__main__': main()
