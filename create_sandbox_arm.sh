#!/bin/bash

# EC2 Sandbox ARM - 环境准备脚本
# 用于快速创建基于 AWS Graviton ARM 处理器的 EC2 沙盒环境并生成配置文件

set -e

# 全局变量
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"      # 脚本目录
DEFAULT_SANDBOX_ROLE="EC2SandboxRole"
DEFAULT_INSTANCE_TYPE="t4g.small"             # AWS Graviton ARM 实例类型
DEFAULT_OS_NAME="Ubuntu 24.04 LTS ARM64"        # 默认操作系统
CREATED_INSTANCE_ID=""        # 传递实例ID

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1" >&2
}
log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" >&2
}
log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" >&2
}
log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# 检查必需的工具
check_requirements() {
    log_info "检查必需的工具..."
    
    local missing_tools=()
    
    if ! command -v aws &> /dev/null; then
        missing_tools+=("aws-cli")
    fi
    
    if ! command -v jq &> /dev/null; then
        missing_tools+=("jq")
    fi
    
    if [ ${#missing_tools[@]} -ne 0 ]; then
        log_error "缺少必需的工具: ${missing_tools[*]}"
        log_info "请安装缺少的工具："
        for tool in "${missing_tools[@]}"; do
            case $tool in
                "aws-cli")
                    echo "  - AWS CLI: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
                    ;;
                "jq")
                    echo "  - jq: sudo apt-get install jq (Ubuntu/Debian) 或 brew install jq (macOS)"
                    ;;
            esac
        done
        exit 1
    fi
    log_success "所有必需工具已安装"
}

# 设置AWS配置
setup_aws_config() {
    local region="$1"
    local aws_profile="$2"
    
    # 设置AWS配置文件
    if [ -n "$aws_profile" ]; then
        export AWS_PROFILE="$aws_profile"
        log_info "使用AWS配置文件: $aws_profile"
    fi
    
    # 确定使用的区域
    if [ -n "$region" ]; then
        export AWS_DEFAULT_REGION="$region"
        log_info "使用指定的AWS区域: $region"
    else
        # 如果没有指定region, 检查配置文件中是否有
        local config_region=$(aws configure get region 2>/dev/null || echo "")
        if [ -z "$config_region" ]; then
            log_error "未设置AWS区域, 请使用 -r 参数指定或配置AWS CLI"
            exit 1
        fi
        log_info "使用配置文件中的AWS区域: $config_region"
    fi
}

# 检查AWS账号配置
check_aws_config() {
    log_info "检查AWS账号配置..."
    
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS凭证未配置或无效"
        log_info "请运行: aws configure"
        exit 1
    fi
    
    local identity=$(aws sts get-caller-identity)
    local account_id=$(echo $identity | jq -r '.Account')
    local user_arn=$(echo $identity | jq -r '.Arn')
    
    log_success "AWS账号配置有效"
    log_info "账户ID: $account_id"
    log_info "用户/角色: $user_arn"
}

# 创建IAM角色（如果不存在）
create_iam_role() {
    local role_name="$DEFAULT_SANDBOX_ROLE"
    
    log_info "检查IAM角色: $role_name"
    
    if aws iam get-role --role-name $role_name &> /dev/null; then
        log_success "IAM角色已存在: $role_name"
        return
    fi
    
    log_info "创建IAM角色: $role_name"
    
    # 检查策略文件是否存在
    if [ ! -f "$SCRIPT_DIR/policies/trust-policy.json" ]; then
        log_error "信任策略文件不存在: $SCRIPT_DIR/policies/trust-policy.json"
        exit 1
    fi
    
    if [ ! -f "$SCRIPT_DIR/policies/sandbox-policy.json" ]; then
        log_error "沙盒策略文件不存在: $SCRIPT_DIR/policies/sandbox-policy.json"
        exit 1
    fi
    
    # 创建角色
    aws iam create-role \
        --role-name $role_name \
        --assume-role-policy-document file://$SCRIPT_DIR/policies/trust-policy.json \
        --description "Role for EC2 Sandbox" > /dev/null
    
    # 附加SSM托管策略
    aws iam attach-role-policy \
        --role-name $role_name \
        --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
    
    # 添加沙盒内联策略
    log_info "添加沙盒内联策略..."
    aws iam put-role-policy \
        --role-name $role_name \
        --policy-name "EC2SandboxPolicy" \
        --policy-document file://$SCRIPT_DIR/policies/sandbox-policy.json
    
    # 创建实例配置文件
    aws iam create-instance-profile --instance-profile-name $role_name > /dev/null
    
    # 将角色添加到实例配置文件
    aws iam add-role-to-instance-profile \
        --instance-profile-name $role_name \
        --role-name $role_name
    
    log_success "IAM角色创建完成: $role_name"
    log_info "附加的策略:"
    log_info "  - AmazonSSMManagedInstanceCore (托管策略)"
    log_info "  - EC2SandboxPolicy (内联策略)"
}

# 创建安全组
create_security_group() {
    local sg_name="ec2-sandbox-sg"
    local sg_description="Security group for EC2 Sandbox - EIC SSH access only"
    
    log_info "检查安全组: $sg_name"
    
    # 获取默认VPC ID
    local vpc_id=$(aws ec2 describe-vpcs --filters "Name=is-default,Values=true" --query 'Vpcs[0].VpcId' --output text)
    
    if [ "$vpc_id" = "None" ] || [ -z "$vpc_id" ]; then
        log_error "未找到默认VPC"
        exit 1
    fi
    
    # 检查安全组是否存在
    local sg_id=$(aws ec2 describe-security-groups \
        --filters "Name=group-name,Values=$sg_name" "Name=vpc-id,Values=$vpc_id" \
        --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "None")
    
    if [ "$sg_id" != "None" ] && [ -n "$sg_id" ]; then
        log_success "安全组已存在: $sg_name ($sg_id)"
        echo $sg_id
        return
    fi
    
    log_info "创建安全组: $sg_name"
    
    # 创建安全组
    sg_id=$(aws ec2 create-security-group \
        --group-name $sg_name \
        --description "$sg_description" \
        --vpc-id $vpc_id \
        --query 'GroupId' --output text)
    
    if [ -z "$sg_id" ] || [ "$sg_id" = "None" ]; then
        log_error "安全组创建失败"
        exit 1
    fi
    
    log_success "安全组创建成功: $sg_id"
    
    # 添加SSH入站规则 - 仅允许EC2 Instance Connect服务访问
    # EC2 Instance Connect的IP范围因区域而异
    local eic_cidr=""
    case $region in
        us-east-1)
            eic_cidr="18.206.107.24/29"
            ;;
        us-east-2)
            eic_cidr="3.16.146.0/29"
            ;;
        us-west-1)
            eic_cidr="13.52.6.112/29"
            ;;
        us-west-2)
            eic_cidr="18.237.140.160/29"
            ;;
        ap-northeast-1)
            eic_cidr="3.112.23.0/29"
            ;;
        ap-northeast-2)
            eic_cidr="13.209.1.56/29"
            ;;
        ap-southeast-1)
            eic_cidr="3.0.5.32/29"
            ;;
        ap-southeast-2)
            eic_cidr="13.239.158.0/29"
            ;;
        eu-west-1)
            eic_cidr="18.202.216.48/29"
            ;;
        eu-central-1)
            eic_cidr="3.120.181.40/29"
            ;;
        *)
            log_warning "未知区域 $region, 使用通用EIC CIDR范围"
            eic_cidr="18.206.107.24/29"  # 默认使用us-east-1的范围
            ;;
    esac
    
    log_info "为区域 $region 添加EIC SSH访问规则 (CIDR: $eic_cidr)"
    
    # 添加SSH入站规则 - 仅允许EIC访问
    if aws ec2 authorize-security-group-ingress \
        --group-id $sg_id \
        --protocol tcp \
        --port 22 \
        --cidr $eic_cidr 2>/dev/null; then
        log_success "EIC SSH规则添加成功"
    else
        log_warning "EIC SSH规则可能已存在"
    fi
    
    # 删除默认的出站规则（如果存在）
    aws ec2 revoke-security-group-egress \
        --group-id $sg_id \
        --protocol -1 \
        --cidr 0.0.0.0/0 2>/dev/null || true
    
    # 添加必要的出站规则
    # HTTPS (443) - 用于下载软件包和AWS API调用
    aws ec2 authorize-security-group-egress \
        --group-id $sg_id \
        --protocol tcp \
        --port 443 \
        --cidr 0.0.0.0/0 2>/dev/null || true
    
    # HTTP (80) - 用于软件包下载
    aws ec2 authorize-security-group-egress \
        --group-id $sg_id \
        --protocol tcp \
        --port 80 \
        --cidr 0.0.0.0/0 2>/dev/null || true
    
    # DNS (53) - 用于域名解析
    aws ec2 authorize-security-group-egress \
        --group-id $sg_id \
        --protocol udp \
        --port 53 \
        --cidr 0.0.0.0/0 2>/dev/null || true
    
    log_success "安全组创建完成: $sg_name ($sg_id)"
    log_info "SSH访问: 仅允许EC2 Instance Connect (EIC)"
    echo $sg_id
}

# 创建EC2实例
create_ec2_instance() {
    local instance_type="${1:-$DEFAULT_INSTANCE_TYPE}"
    local ami_id="${2:-}"
    local instance_name="sandbox-instance-$instance_type"

    log_info "准备创建EC2实例: $instance_name"
    
    # 如果没有指定AMI, 自动选择最新的Ubuntu 24.04 LTS (ARM64)
    if [ -z "$ami_id" ]; then
        log_info "查找最新的 $DEFAULT_OS_NAME AMI..."
        ami_id=$(aws ec2 describe-images \
            --owners 099720109477 \
            --filters "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-arm64-server-*" "Name=state,Values=available" \
            --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
            --output text)
        
        if [ -z "$ami_id" ] || [ "$ami_id" = "None" ]; then
            log_error "无法找到$DEFAULT_OS_NAME AMI"
            exit 1
        fi
        
        log_info "使用AMI: $ami_id ($DEFAULT_OS_NAME)"
    fi
    
    # 创建安全组
    local sg_id=$(create_security_group)
    
    log_info "创建EC2实例..."

    # 检查用户数据脚本
    if [ ! -f "$SCRIPT_DIR/scripts/user-data.sh" ]; then
        log_error "用户数据脚本不存在: $SCRIPT_DIR/scripts/user-data.sh"
        exit 1
    fi
    
    # 启动实例 - 不使用密钥对, 通过SSM和EIC访问
    local instance_id=$(aws ec2 run-instances \
        --image-id $ami_id \
        --count 1 \
        --instance-type $instance_type \
        --security-group-ids $sg_id \
        --iam-instance-profile Name=$DEFAULT_SANDBOX_ROLE \
        --user-data file://"$SCRIPT_DIR/scripts/user-data.sh" \
        --metadata-options "HttpTokens=required,HttpPutResponseHopLimit=2,HttpEndpoint=enabled" \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$instance_name},{Key=Purpose,Value=Sandbox},{Key=OS,Value=Ubuntu-24.04},{Key=Access,Value=SSM-EIC},{Key=DataAnalysis,Value=Enabled}]" \
        --query 'Instances[0].InstanceId' \
        --output text)
    
    if [ -z "$instance_id" ] || [ "$instance_id" = "None" ]; then
        log_error "实例创建失败"
        exit 1
    fi
    
    # 将实例ID保存到全局变量
    CREATED_INSTANCE_ID="$instance_id"
    
    log_success "实例创建成功: $instance_id"
    
    # 等待实例运行
    log_info "等待实例启动..."
    aws ec2 wait instance-running --instance-ids $instance_id
    
    # 等待SSM Agent就绪
    log_info "等待SSM Agent就绪..."
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if aws ssm describe-instance-information \
            --filters "Key=InstanceIds,Values=$instance_id" \
            --query 'InstanceInformationList[0].PingStatus' \
            --output text 2>/dev/null | grep -q "Online"; then
            break
        fi
        
        attempt=$((attempt + 1))
        log_info "等待SSM Agent就绪... ($attempt/$max_attempts)"
        sleep 10
    done
    
    if [ $attempt -eq $max_attempts ]; then
        log_warning "SSM Agent可能未完全就绪, 但实例已创建"
    else
        log_success "SSM Agent已就绪"
    fi
    
    # 获取实例信息
    local instance_info=$(aws ec2 describe-instances --instance-ids $instance_id --query 'Reservations[0].Instances[0]')
    local public_ip=$(echo $instance_info | jq -r '.PublicIpAddress // "N/A"')
    local private_ip=$(echo $instance_info | jq -r '.PrivateIpAddress')
    local az=$(echo $instance_info | jq -r '.Placement.AvailabilityZone')
    
    log_success "实例信息:"
    echo "  实例ID: $instance_id"
    echo "  实例类型: $instance_type (AWS Graviton ARM)"
    echo "  操作系统: $DEFAULT_OS_NAME"
    echo "  可用区: $az"
    echo "  公网IP: $public_ip"
    echo "  私网IP: $private_ip"
    echo "  安全组: $sg_id"
    echo "  访问方式: SSM Session Manager + EC2 Instance Connect"
    echo ""
    echo "SSH连接命令 (使用EIC):"
    if [ "$public_ip" != "N/A" ]; then
        echo "  aws ec2-instance-connect ssh \\"
        echo "    --instance-id $instance_id \\"
        echo "    --os-user ubuntu"
        echo ""
    else
        echo "  (等待公网IP分配)"
    fi
    echo ""
    echo "SSM连接命令:"
    echo "  aws ssm start-session --target $instance_id"
}

# 生成沙盒环境 JSON 配置对象
generate_sandbox_json() {
    local environment_name=$1

    cat << EOF
{
  "$environment_name": {
    "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
    "instance_id": "$instance_id",
    "region": "$region",
    "aws_profile": "$aws_profile",
    "base_sandbox_dir": "/opt/sandbox",
    "max_execution_time": 900,
    "max_memory_mb": 1024,
    "cleanup_after_hours": 48,
    "allowed_runtimes": ["python", "node", "bash", "sh"]
  }
}
EOF
}

# 生成沙盒环境配置文件
generate_config() {
    local instance_id=$1
    local environment_name="sandbox-$instance_type"

    log_info "生成配置文件..."
    
    # 生成新的沙盒配置 JSON
    local new_sandbox_json=$(generate_sandbox_json $environment_name)
    local temp_config=$(mktemp)

    # 检查配置文件是否存在
    if [ -f "config.json" ]; then
        log_info "更新配置文件..."
        jq --argjson new_config "$new_sandbox_json" '. + $new_config' config.json > "$temp_config" && mv "$temp_config" config.json
        log_success "已添加新的沙盒环境配置: $environment_name"
    else
        log_info "创建配置文件..."
        cat > config.json << EOF
{
  "_comment": "EC2 Sandbox Configuration - Auto-generated",
  "_generated": {
    "script_version": "1.5.0",
    "access_method": "SSM + EIC"
  }
}
EOF
        jq --argjson sandbox_config "$new_sandbox_json" '. + $sandbox_config' config.json > "$temp_config" && mv "$temp_config" config.json
        log_success "已经生成配置文件: config.json 及 环境配置: $environment_name"
    fi
}

# 测试连接
test_connection() {
    local instance_id=$1
    
    log_info "测试沙盒连接..."
    
    # 简单的连接测试
    local test_result=$(aws ssm send-command \
        --instance-ids $instance_id \
        --document-name "AWS-RunShellScript" \
        --parameters 'commands=["echo \"Connection test successful\""]' \
        --query 'Command.CommandId' \
        --output text)
    
    if [ -z "$test_result" ] || [ "$test_result" = "None" ]; then
        log_error "连接测试失败"
        return 1
    fi
    
    # 等待命令完成
    sleep 5
    
    local output=$(aws ssm get-command-invocation \
        --command-id $test_result \
        --instance-id $instance_id \
        --query 'StandardOutputContent' \
        --output text 2>/dev/null || echo "")
    
    if echo "$output" | grep -q "Connection test successful"; then
        log_success "沙盒连接测试成功"
        return 0
    else
        log_warning "连接测试可能未完全成功, 但实例已准备就绪"
        return 0
    fi
}

# 主函数
main() {
    echo "=================================="
    echo "EC2 Sandbox - 环境准备脚本"
    echo "=================================="
    echo
    
    # 解析参数 - 使用全局变量, 供所有函数访问
    instance_type="$DEFAULT_INSTANCE_TYPE"  # 实例类型
    ami_id=""                               # AMI ID
    region=""                               # AWS区域
    aws_profile=""                          # AWS配置文件
    skip_test=false                         # 是否跳过测试
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -t|--type)
                instance_type="$2"
                shift 2
                ;;
            -a|--ami)
                ami_id="$2"
                shift 2
                ;;
            -r|--region)
                region="$2"
                shift 2
                ;;
            -p|--profile)
                aws_profile="$2"
                shift 2
                ;;
            --skip-test)
                skip_test=true
                shift
                ;;
            -h|--help)
                echo "用法: $0 [选项]"
                echo
                echo "🚀 EC2 Sandbox ARM 环境创建脚本 (基于 AWS Graviton 处理器)"
                echo
                echo "选项:"
                echo "  -t, --type TYPE         EC2实例类型 (默认: $DEFAULT_INSTANCE_TYPE - Graviton ARM)"
                echo "  -a, --ami AMI_ID        指定AMI ID (默认: 最新$DEFAULT_OS_NAME)"
                echo "  -r, --region REGION     AWS区域 (默认: 从AWS配置读取)"
                echo "  -p, --profile PROFILE   AWS配置文件 (默认: default)"
                echo "  --skip-test             跳过连接测试"
                echo "  -h, --help              显示帮助信息"
                echo
                echo "特性:"
                echo "  - 🏗️ 基于 AWS Graviton ARM 处理器 (高性价比)"
                echo "  - 🔐 通过SSM Session Manager和EC2 Instance Connect访问"
                echo "  - 🛡️ 安全组仅允许EIC访问SSH端口"
                echo "  - 🐍 预装Python 3、Node.js和常用开发工具"
                echo "  - 📊 预装完整的数据分析库 (pandas, matplotlib, plotly, scipy等)"
                echo
                echo "推荐的 Graviton 实例类型:"
                echo "  - t4g.nano    (2 vCPU, 0.5 GB RAM) - 最小配置"
                echo "  - t4g.micro   (2 vCPU, 1 GB RAM)   - 轻量使用"
                echo "  - t4g.small   (2 vCPU, 2 GB RAM)   - 基础开发"
                echo "  - t4g.medium  (2 vCPU, 4 GB RAM)   - 推荐配置"
                echo "  - t4g.large   (2 vCPU, 8 GB RAM)   - 重度使用"
                echo
                echo "示例:"
                echo "  $0                                   # 使用默认设置($DEFAULT_INSTANCE_TYPE)"
                echo "  $0 -t c7g.small                      # 使用c7g.small实例"
                echo "  $0 -r us-west-2 -p my-profile        # 指定区域和配置文件"
                echo "  $0 -t t4g.large --skip-test          # 使用t4g.large并跳过测试"
                exit 0
                ;;
            *)
                log_error "未知参数: $1"
                echo "使用 -h 或 --help 查看帮助"
                exit 1
                ;;
        esac
    done
    
    # 执行步骤
    setup_aws_config "$region" "$aws_profile"
    check_requirements
    check_aws_config
    create_iam_role
    
    # 调用函数创建实例, 实例ID保存在全局变量中
    create_ec2_instance "$instance_type" "$ami_id"
    
    if [ -n "$CREATED_INSTANCE_ID" ] && [ "$CREATED_INSTANCE_ID" != "None" ]; then
        generate_config "$CREATED_INSTANCE_ID"
        
        if [ "$skip_test" = false ]; then
            test_connection "$CREATED_INSTANCE_ID"
        fi
    else
        log_error "实例创建失败, 跳过后续步骤"
        exit 1
    fi
    
    echo
    log_success "EC2沙盒环境准备完成！"
    echo
    echo "下一步："
    echo "1. 检查配置文件: config.json"
    echo "2. 运行测试: python test_sandbox.py"
    echo "3. 查看示例: python demo.py"
    echo
    echo "配置管理命令："
    echo "  python config_manager.py --list      # 列出环境"
    echo "  python config_manager.py --validate  # 验证配置"
    echo
}

# 运行主函数
main "$@"
