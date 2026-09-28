"""Optional FastAPI transport. Use `python -m incidentatlas serve --fastapi`."""
from pathlib import Path
import json
from .service import Service
MAX_BODY=5*1024*1024


def create_app(db_path='.incidentatlas/state.sqlite3', web_root=None):
    from fastapi import FastAPI,Request
    from fastapi.responses import JSONResponse,Response,FileResponse
    app=FastAPI(title='IncidentAtlas',version='0.1.0',description='Local evidence-first incident investigation. No production authentication.')
    service=Service(db_path)
    app.state.service=service
    root=Path(web_root) if web_root else Path(__file__).resolve().parent.parent/'web'
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def lifespan(app):
        yield
        service.store.close()
    app.router.lifespan_context=lifespan

    @app.api_route('/api/{route:path}',methods=['GET','POST','PATCH'])
    async def api_route(route: str, request: Request):
        try:
            body=None
            if request.method in {'POST','PATCH'}:
                chunks=[]; size=0
                async for chunk in request.stream():
                    size+=len(chunk)
                    if size>MAX_BODY: return JSONResponse({'error':'body exceeds 5 MiB'},status_code=413)
                    chunks.append(chunk)
                data=b''.join(chunks)
                body=json.loads(data) if data else {}
            # A single local app; blocking disk work is executed in a worker thread.
            from starlette.concurrency import run_in_threadpool
            result=await run_in_threadpool(service.dispatch,request.method,str(request.url),body)
            return Response(result,media_type='text/markdown') if isinstance(result,str) else JSONResponse(result)
        except (ValueError,TypeError,json.JSONDecodeError) as exc: return JSONResponse({'error':str(exc)},status_code=400)
        except KeyError as exc: return JSONResponse({'error':str(exc).strip("'")},status_code=404)

    @app.get('/{path:path}',include_in_schema=False)
    def static(path: str):
        candidate=(root/(path or 'index.html')).resolve()
        if not candidate.is_relative_to(root.resolve()) or not candidate.is_file():
            return JSONResponse({'error':'file not found'},status_code=404)
        return FileResponse(candidate)
    return app
