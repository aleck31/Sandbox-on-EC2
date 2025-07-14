#!/bin/bash

# EC2 GPU Sandbox - 环境准备脚本
# 用于快速创建基于 AWS EC2 GPU 沙盒环境并生成配置文件

set -e

# 全局变量
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"      # 脚本目录
DEFAULT_SANDBOX_ROLE="EC2SandboxRole"
DEFAULT_INSTANCE_TYPE="g4dn.xlarge"           # 默认GPU实例类型
DEFAULT_OS_NAME="Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)"  # 默认操作系统
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
    
    local account_id=$(aws sts get-caller-identity --query Account --output text)
    local user_arn=$(aws sts get-caller-identity --query Arn --output text)
    log_success "AWS账号验证成功"
    log_info "账号ID: $account_id"
    log_info "用户ARN: $user_arn"
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
    local vpc_id=$(aws ec2 describe-vpcs --filters "Name=is-default,Values=true" --query "Vpcs[0].VpcId" --output text)
    if [ "$vpc_id" = "None" ] || [ -z "$vpc_id" ]; then
        log_error "未找到默认VPC，请确保账号中存在默认VPC"
        exit 1
    fi
    log_info "使用默认VPC: $vpc_id"
    
    # 检查安全组是否存在
    local existing_sg_id=$(aws ec2 describe-security-groups \
        --filters "Name=group-name,Values=$sg_name" "Name=vpc-id,Values=$vpc_id" \
        --query "SecurityGroups[0].GroupId" --output text 2>/dev/null || echo "None")
    
    if [ "$existing_sg_id" != "None" ] && [ -n "$existing_sg_id" ]; then
        log_info "安全组已存在: $existing_sg_id"
        echo "$existing_sg_id"
        return
    fi
    
    log_info "创建安全组: $sg_name"
    local sg_id=$(aws ec2 create-security-group \
        --group-name "$sg_name" \
        --description "$sg_description" \
        --vpc-id "$vpc_id" \
        --query "GroupId" --output text)
    
    log_success "安全组创建成功: $sg_id"
    
    # 添加入站规则 - 只允许EIC访问SSH
    log_info "配置安全组规则..."
    
    # 获取当前区域的EIC服务IP范围
    local region=$(aws configure get region)
    local eic_prefix=""
    
    case "$region" in
        us-east-1) eic_prefix="18.206.107.24/29" ;;
        us-east-2) eic_prefix="3.16.146.0/29" ;;
        us-west-1) eic_prefix="13.52.6.112/29" ;;
        us-west-2) eic_prefix="18.237.140.160/29" ;;
        eu-west-1) eic_prefix="18.202.216.48/29" ;;
        eu-central-1) eic_prefix="3.120.181.40/29" ;;
        ap-southeast-1) eic_prefix="13.239.158.0/29" ;;
        ap-northeast-1) eic_prefix="3.112.23.0/29" ;;
        *) 
            log_warning "未知区域 $region，使用通用EIC配置"
            eic_prefix="0.0.0.0/0"  # 作为后备方案
            ;;
    esac
    
    # 添加SSH访问规则（仅限EIC）
    if [ "$eic_prefix" != "0.0.0.0/0" ]; then
        aws ec2 authorize-security-group-ingress \
            --group-id "$sg_id" \
            --protocol tcp \
            --port 22 \
            --cidr "$eic_prefix" \
            --description "SSH access via EC2 Instance Connect" 2>/dev/null || true
        log_info "已添加SSH访问规则 (EIC): $eic_prefix"
    else
        log_warning "使用开放SSH访问，建议在生产环境中限制访问"
        aws ec2 authorize-security-group-ingress \
            --group-id "$sg_id" \
            --protocol tcp \
            --port 22 \
            --cidr "0.0.0.0/0" \
            --description "SSH access (open - consider restricting)" 2>/dev/null || true
    fi
    
    # 添加出站规则（允许所有出站流量）
    aws ec2 authorize-security-group-egress \
        --group-id "$sg_id" \
        --protocol -1 \
        --cidr "0.0.0.0/0" \
        --description "All outbound traffic" 2>/dev/null || true
    
    log_success "安全组配置完成: $sg_id"
    echo "$sg_id"
}
# 创建EC2实例
create_ec2_instance() {
    local instance_type="${1:-$DEFAULT_INSTANCE_TYPE}"
    local ami_id="${2:-}"
    local instance_name="sandbox-instance-$instance_type"
    local security_group_id="$3"
    
    log_info "创建GPU EC2实例..."
    log_info "实例类型: $instance_type"
    
    # 如果没有指定AMI，查找最新的Deep Learning AMI
    if [ -z "$ami_id" ]; then
        log_info "查找最新的Deep Learning GPU AMI..."
        ami_id=$(aws ec2 describe-images \
            --owners amazon \
            --filters \
                "Name=name,Values=Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)*" \
                "Name=state,Values=available" \
                "Name=architecture,Values=x86_64" \
            --query "Images | sort_by(@, &CreationDate) | [-1].ImageId" \
            --output text)
        
        if [ "$ami_id" = "None" ] || [ -z "$ami_id" ]; then
            log_error "未找到合适的Deep Learning GPU AMI"
            exit 1
        fi
        log_info "使用AMI: $ami_id"
    fi
    
    # 获取AMI详细信息
    local ami_info=$(aws ec2 describe-images --image-ids "$ami_id" --query "Images[0]" 2>/dev/null || echo "null")
    if [ "$ami_info" = "null" ]; then
        log_error "无效的AMI ID: $ami_id"
        exit 1
    fi
    
    local ami_name=$(echo "$ami_info" | jq -r '.Name // "Unknown"')
    local ami_description=$(echo "$ami_info" | jq -r '.Description // "No description"')
    log_info "AMI名称: $ami_name"
    log_info "AMI描述: $ami_description"
    
    # 读取用户数据脚本
    local user_data_file="$SCRIPT_DIR/scripts/user-data-gpu.sh"
    if [ ! -f "$user_data_file" ]; then
        log_error "用户数据脚本不存在: $user_data_file"
        exit 1
    fi
    
    # 创建实例
    log_info "启动EC2实例..."
    local run_result=$(aws ec2 run-instances \
        --image-id "$ami_id" \
        --count 1 \
        --instance-type "$instance_type" \
        --security-group-ids "$security_group_id" \
        --iam-instance-profile Name="$DEFAULT_SANDBOX_ROLE" \
        --user-data "file://$user_data_file" \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$instance_name},{Key=Purpose,Value=GPU-Sandbox},{Key=CreatedBy,Value=create-sandbox-gpu-script}]" \
        --metadata-options "HttpTokens=required,HttpPutResponseHopLimit=2,HttpEndpoint=enabled" \
        --monitoring Enabled=true)
    
    local instance_id=$(echo "$run_result" | jq -r '.Instances[0].InstanceId')
    CREATED_INSTANCE_ID="$instance_id"
    
    log_success "EC2实例创建成功: $instance_id"
    log_info "实例名称: $instance_name"
    
    # 等待实例运行
    log_info "等待实例启动..."
    aws ec2 wait instance-running --instance-ids "$instance_id"
    log_success "实例已启动"
    
    # 获取实例详细信息
    local instance_info=$(aws ec2 describe-instances --instance-ids "$instance_id" --query "Reservations[0].Instances[0]")
    local public_ip=$(echo "$instance_info" | jq -r '.PublicIpAddress // "N/A"')
    local private_ip=$(echo "$instance_info" | jq -r '.PrivateIpAddress // "N/A"')
    local az=$(echo "$instance_info" | jq -r '.Placement.AvailabilityZone // "N/A"')
    
    log_info "实例详情:"
    log_info "  实例ID: $instance_id"
    log_info "  公网IP: $public_ip"
    log_info "  私网IP: $private_ip"
    log_info "  可用区: $az"
    
    # 等待系统状态检查通过
    log_info "等待系统状态检查..."
    aws ec2 wait system-status-ok --instance-ids "$instance_id"
    log_success "系统状态检查通过"
    
    # 等待用户数据脚本执行完成
    log_info "等待GPU环境初始化完成（这可能需要几分钟）..."
    sleep 60  # 给用户数据脚本一些时间开始执行
    
    echo "$instance_id"
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
    "max_execution_time": 600,
    "max_memory_mb": 4096,
    "cleanup_after_hours": 48,
    "allowed_runtimes": ["python", "node", "bash", "sh"]
  }
}
EOF
}

# 生成沙盒环境配置文件
generate_config() {
    local instance_id="$1"
    local environment_name="sandbox-$instance_type"
    
    log_info "生成配置文件..."
    
    # 生成新的沙盒配置 JSON
    local new_sandbox_json=$(generate_sandbox_json $environment_name)
    local temp_config=$(mktemp)
    
    # 检查配置文件是否存在
    if [ -f "$SCRIPT_DIR/config.json" ]; then
        log_info "更新配置文件..."
        jq --argjson new_config "$new_sandbox_json" '. + $new_config' "$SCRIPT_DIR/config.json" > "$temp_config" && mv "$temp_config" "$SCRIPT_DIR/config.json"
        log_success "已添加新的GPU沙盒环境配置: $environment_name"
    else
        log_info "创建配置文件..."
        cat > "$SCRIPT_DIR/config.json" << EOF
{
  "_comment": "EC2 GPU Sandbox Configuration - Auto-generated",
  "_generated": {
    "script_version": "1.0.0",
    "access_method": "SSM + EIC",
    "gpu_support": true
  }
}
EOF
        jq --argjson sandbox_config "$new_sandbox_json" '. + $sandbox_config' "$SCRIPT_DIR/config.json" > "$temp_config" && mv "$temp_config" "$SCRIPT_DIR/config.json"
        log_success "已经生成配置文件: config.json 及 GPU环境配置: $environment_name"
    fi
    
    log_success "配置文件生成完成"
    log_info "配置名称: $environment_name"
}

# 测试连接
test_connection() {
    local instance_id="$1"
    
    log_info "测试与实例的连接..."
    
    # 测试SSM连接
    log_info "测试SSM连接..."
    local ssm_test=$(aws ssm describe-instance-information \
        --filters "Key=InstanceIds,Values=$instance_id" \
        --query "InstanceInformationList[0].PingStatus" \
        --output text 2>/dev/null || echo "Failed")
    
    if [ "$ssm_test" = "Online" ]; then
        log_success "SSM连接正常"
    else
        log_warning "SSM连接可能需要更多时间初始化"
    fi
    
    # GPU环境初始化提示
    log_info "GPU环境初始化中..."
    log_info "请等待几分钟让GPU环境完全初始化完成"
    log_success "🎉 GPU沙盒环境创建完成！"
    log_info "环境准备完成，可以开始使用GPU沙盒！"
}

# 主函数
main() {
    log_info "🚀 开始创建EC2 GPU沙盒环境..."
    
    # 解析参数 - 使用全局变量, 供所有函数访问
    instance_type="$DEFAULT_INSTANCE_TYPE"  # 实例类型
    ami_id=""                               # AMI ID
    region=""                               # AWS区域
    aws_profile=""                          # AWS配置文件
    
    # 解析命令行参数
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
            -h|--help)
                echo "EC2 GPU Sandbox 环境创建脚本"
                echo
                echo "用法: $0 [选项]"
                echo
                echo "选项:"
                echo "  -t, --type TYPE         EC2实例类型 (默认: $DEFAULT_INSTANCE_TYPE)"
                echo "  -a, --ami AMI_ID        指定AMI ID (默认: 最新Deep Learning GPU AMI)"
                echo "  -r, --region REGION     AWS区域 (默认: 从AWS配置读取)"
                echo "  -p, --profile PROFILE   AWS配置文件名称"
                echo "  -h, --help              显示此帮助信息"
                echo
                echo "GPU实例类型推荐:"
                echo "  g4dn.xlarge    - 1x NVIDIA T4, 4 vCPU, 16GB RAM (经济型)"
                echo "  g4dn.2xlarge   - 1x NVIDIA T4, 8 vCPU, 32GB RAM (平衡型)"
                echo "  g5.xlarge      - 1x NVIDIA A10G, 4 vCPU, 16GB RAM (新一代)"
                echo "  g5.2xlarge     - 1x NVIDIA A10G, 8 vCPU, 32GB RAM (推荐)"
                echo "  p3.2xlarge     - 1x NVIDIA V100, 8 vCPU, 61GB RAM (高性能)"
                echo
                echo "示例:"
                echo "  $0                                   # 使用默认设置($DEFAULT_INSTANCE_TYPE)"
                echo "  $0 -t g5.2xlarge                    # 使用g5.2xlarge实例"
                echo "  $0 -r us-west-2 -p my-profile       # 指定区域和配置文件"
                echo "  $0 -t g4dn.2xlarge -r eu-west-1     # 指定实例类型和区域"
                exit 0
                ;;
            *)
                log_error "未知参数: $1"
                echo "使用 $0 --help 查看帮助信息"
                exit 1
                ;;
        esac
    done
    
    # 验证GPU实例类型
    if [[ ! "$instance_type" =~ ^(g4dn|g5|p3|p4) ]]; then
        log_warning "实例类型 '$instance_type' 可能不支持GPU"
        read -p "是否继续? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "操作已取消"
            exit 0
        fi
    fi
    
    # 执行创建流程
    check_requirements
    setup_aws_config "$region" "$aws_profile"
    check_aws_config
    create_iam_role

    local security_group_id=$(create_security_group)
    local instance_id=$(create_ec2_instance "$instance_type" "$ami_id" "$security_group_id")
    
    generate_config "$instance_id"
    test_connection "$instance_id"
    
    # 显示完成信息
    echo
    log_success "🎉 GPU沙盒环境创建完成！"
    echo
    echo "📋 环境信息:"
    echo "  实例ID: $instance_id"
    echo "  实例类型: $instance_type"
    echo "  区域: $region"
    echo "  配置文件: $SCRIPT_DIR/config.json"
    echo
    echo "🔗 连接方式:"
    echo "  1. EC2 Instance Connect:"
    echo "     aws ec2-instance-connect send-ssh-public-key \\"
    echo "       --instance-id $instance_id \\"
    echo "       --availability-zone $(aws ec2 describe-instances --instance-ids $instance_id --query 'Reservations[0].Instances[0].Placement.AvailabilityZone' --output text) \\"
    echo "       --instance-os-user ubuntu \\"
    echo "       --ssh-public-key file://~/.ssh/id_rsa.pub"
    echo "     ssh ubuntu@$(aws ec2 describe-instances --instance-ids $instance_id --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)"
    echo
    echo "  2. SSM Session Manager:"
    echo "     aws ssm start-session --target $instance_id"
    echo
    echo "🚀 GPU环境使用:"
    echo "  # 验证GPU环境"
    echo "  python /opt/sandbox/verify_gpu.py"
    echo
    echo "  # 查看GPU状态"
    echo "  nvidia-smi"
    echo
    echo "📚 更多信息:"
    echo "  - 初始化日志: /var/log/gpu-sandbox-init.log"
    echo "  - GPU环境脚本: /opt/sandbox/activate_gpu.sh"
    echo "  - 沙盒目录: /opt/sandbox"
    echo
    log_info "环境准备完成，可以开始使用GPU沙盒！"
}

# 运行主函数
main "$@"
