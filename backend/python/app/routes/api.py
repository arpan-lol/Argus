from fastapi import APIRouter
from app.controllers import workspace

router=APIRouter()

router.add_api_route("/health", workspace.health, methods=["GET"])
router.add_api_route("/corpus", workspace.collection, methods=["GET"])
router.add_api_route("/documents", workspace.documents, methods=["GET"])
router.add_api_route("/documents/{identifier}", workspace.document, methods=["GET"])
router.add_api_route("/map/overview", workspace.overview, methods=["GET"])
router.add_api_route("/map/view", workspace.view, methods=["GET"])
router.add_api_route("/map/locate/{identifier}", workspace.locate, methods=["GET"])
router.add_api_route("/map/node/{identifier}", workspace.node, methods=["GET"])
router.add_api_route("/map/neighborhood/{identifier}", workspace.neighborhood, methods=["GET"])
router.add_api_route("/graph", workspace.inspect, methods=["GET"])
router.add_api_route("/graph/diagnostics", workspace.diagnostics, methods=["GET"])
router.add_api_route("/graph/sync", workspace.sync, methods=["POST"], status_code=409)
router.add_api_route("/search", workspace.search, methods=["POST"])
router.add_api_route("/runs", workspace.runs, methods=["GET"])
router.add_api_route("/runs/{identifier}", workspace.run, methods=["GET"])
