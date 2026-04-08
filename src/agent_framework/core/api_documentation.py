"""
API 文档生成系统
基于 Flask-RESTX 自动生成 Swagger/OpenAPI 文档
"""

from flask import Blueprint
from flask_restx import Api, Resource, fields, Namespace

# 创建 API 文档
api_doc_bp = Blueprint('api_doc', __name__, url_prefix='/api')

api = Api(
    api_doc_bp,
    version='1.0.0',
    title='Agent Framework API',
    description='智能 AI 应用开发平台 API 文档',
    doc='/docs',
    prefix='/api'
)

# 命名空间
workflows_ns = Namespace('workflows', description='工作流管理')
agents_ns = Namespace('agents', description='Agent 管理')
knowledge_ns = Namespace('knowledge', description='知识库管理')
auth_ns = Namespace('auth', description='用户认证')

api.add_namespace(workflows_ns)
api.add_namespace(agents_ns)
api.add_namespace(knowledge_ns)
api.add_namespace(auth_ns)

# 数据模型
workflow_model = api.model('Workflow', {
    'id': fields.String(required=True, description='工作流ID'),
    'name': fields.String(required=True, description='工作流名称'),
    'description': fields.String(description='描述'),
    'nodes': fields.List(fields.Raw, description='节点列表'),
    'edges': fields.List(fields.Raw, description='边列表'),
    'created_at': fields.DateTime(description='创建时间'),
})

user_model = api.model('User', {
    'user_id': fields.String(description='用户ID'),
    'username': fields.String(required=True, description='用户名'),
    'email': fields.String(required=True, description='邮箱'),
    'role': fields.String(description='角色'),
})

# 工作流 API
@workflows_ns.route('/')
class WorkflowList(Resource):
    @workflows_ns.doc('list_workflows')
    @workflows_ns.marshal_list_with(workflow_model)
    def get(self):
        """获取工作流列表"""
        return []

    @workflows_ns.doc('create_workflow')
    @workflows_ns.expect(workflow_model)
    @workflows_ns.marshal_with(workflow_model, code=201)
    def post(self):
        """创建工作流"""
        return {}, 201


@workflows_ns.route('/<string:workflow_id>')
class Workflow(Resource):
    @workflows_ns.doc('get_workflow')
    @workflows_ns.marshal_with(workflow_model)
    def get(self, workflow_id):
        """获取工作流详情"""
        return {}

    @workflows_ns.doc('update_workflow')
    @workflows_ns.expect(workflow_model)
    @workflows_ns.marshal_with(workflow_model)
    def put(self, workflow_id):
        """更新工作流"""
        return {}

    @workflows_ns.doc('delete_workflow')
    def delete(self, workflow_id):
        """删除工作流"""
        return {'message': '删除成功'}


# 认证 API
@auth_ns.route('/login')
class Login(Resource):
    @auth_ns.doc('login')
    def post(self):
        """用户登录"""
        return {'token': 'xxx'}


@auth_ns.route('/register')
class Register(Resource):
    @auth_ns.doc('register')
    @auth_ns.expect(user_model)
    def post(self):
        """用户注册"""
        return {'message': '注册成功'}, 201
