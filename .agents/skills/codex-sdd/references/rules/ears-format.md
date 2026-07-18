# EARS 格式指南

## 概述

EARS（Easy Approach to Requirements Syntax）是规格驱动开发中验收标准的标准格式。  

EARS 模式描述需求的逻辑结构（条件 + 主体 + 响应），不绑定于任何特定自然语言。所有验收标准应使用规格配置的目标语言编写（例如 spec.json.language / zh-CN）。  
保留 EARS 触发关键词和固定短语为英文（When、If、While、Where、The system shall），  
仅将变量部分（[event]、[precondition]、[trigger]、[feature is included]、[response/action]）本地化为目标语言。不要在触发词或固定英文短语内部混入目标语言文本。  

## 主要 EARS 模式

### 1. 事件驱动需求

模式：When [event], the [system] shall [response/action]  
适用场景：对特定事件或触发的响应  
示例：When user clicks checkout button, the Checkout Service shall validate cart contents  

### 2. 状态驱动需求

模式：While [precondition], the [system] shall [response/action]  
适用场景：依赖于系统状态或前置条件的行为  
示例：While payment is processing, the Checkout Service shall display loading indicator  

### 3. 非预期行为需求

模式：If [trigger], the [system] shall [response/action]  
适用场景：系统对错误、故障或不希望出现的情况的响应  
示例：If invalid credit card number is entered, then the website shall display error message  

### 4. 可选功能需求

模式：Where [feature is included], the [system] shall [response/action]  
适用场景：可选或条件性功能的需求  
示例：Where the car has a sunroof, the car shall have a sunroof control panel  

### 5. 普遍需求

模式：The [system] shall [response/action]  
适用场景：始终活跃的需求和系统基本属性  
示例：The mobile phone shall have a mass of less than 100 grams  

## 组合模式

While [precondition], when [event], the [system] shall [response/action]  
When [event] and [additional condition], the [system] shall [response/action]  

## 主体选择指南

软件项目：使用具体的系统/服务名称（如 "Checkout Service"、"User Auth Module"）  
流程/工作流：使用负责的团队/角色（如 "Support Team"、"Review Process"）  
非软件：使用适当的主体（如 "Marketing Campaign"、"Documentation"）  

## 质量标准

需求必须是可测试的、可验证的，且描述单一行为。  
使用客观语言：强制行为使用 "shall"，推荐行为使用 "should"；避免模糊术语。  
遵循 EARS 语法：[condition], the [system] shall [response/action]。  
