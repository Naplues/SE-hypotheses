# 面向 FSE 的全实验结果报告

日期：2026-10-02。状态：可追溯的分析与论文论证草案，尚非可直接提交的最终研究报告。机器核检已执行；独立人工假设审定、行为标注及异常任务重评尚未完成。本文不保证录用，不以调整叙事代替补齐科学证据。

数据根目录：`/Users/gzq/Repo/FSE2027`。全部分析只读取既有实验，不修改原始提示、补丁、评测结果或论文。

## 一、总体判断：有论文素材，但主张必须调整

现有数据不支持“误导假设普遍降低修复率”，也没有足够证据证明“代理普遍能识别反证并恢复”。更可靠的观察是：在一个固定代理—模型配置上，五类提示条件的单轮平均成功率接近；补充运行暴露了首轮混合结果任务的较高运行变异；提示条件能改变部分搜索和工具成本；少数局部失败路径能跨轮重复，而部分看似稳定的条件差异实际上来自评测不一致。[C01–C08]

建议中心问题从“误导是否使代理失败”转为：

> 诊断先验如何改变仓库级修复过程，哪些观察到的结果差异能跨运行复现，以及如何避免把运行与评测波动误认成上下文敏感性？

这不是将负结果包装成正结果，而是由重复实验和审计明确收缩因果解释。以当前数据直接提交，主要风险是操纵语义有效性、行为机制缺乏独立标注、单配置外推和已有相关工作的重合。最有价值的下一步是把这四个问题中的关键缺口补齐，而不是增加表格数量或追求显著性。

## 二、数据全景与正确分母

### 2.1 主实验与补充实验

| 数据层 | 任务 | 条件 | 每任务—条件执行数 | 运行数 | 合理用途 |
|---|---:|---:|---:|---:|---|
| 原始五组 | 272 | 5 | 1 | 1,360 | 选定任务集的平均结果与过程对比 |
| 初始结果混合组补充 | 34 | 5 | 2 | 340 | 首轮差异模式的重复性与运行变异 |
| 初始结果稳定组补充 | 50 | 5 | 2 | 500 | 稳定性复核与过程效果复核 |
| 合计唯一执行 | 272个独特任务 | 5 | 不平衡：84任务3次，其余188任务1次 | 2,200 | 分层分析，不能当成2,200个独立样本 |

重复实验中的原始420条记录已经包含在1,360条主实验中，不再重复计数。原始评测有1,356个标签、4个缺失；新增840条均有汇总结果，空补丁按失败记入新增结果。因此全实验有2,196个可用运行标签，但统计独立性仍以任务为核心。[C01]

原始任务覆盖12个Python项目：Django116、SymPy34、scikit-learn27、Sphinx19、xarray18、Matplotlib16、pytest15、Astropy13、Pylint8、Requests4、Seaborn1、Flask1。Django占42.6%，不应将“12项目”理解为项目分布均衡。[E01]

原始全条件标签齐全的任务为269个，其中191个五条件均成功、44个五条件均失败、34个初始结果混合。补充稳定组是从前两层抽出的41个全成功任务与9个全失败任务，不是无条件随机样本；敏感组是34个混合任务的全纳入。后续成功率不能与全272任务的首轮成功率直接比较来宣称模型进步或退化。[C03]

### 2.2 条件与解释边界

ORIG为原始问题描述；CH为开发者补丁导出的定位、原因和修复指导；WLH、WCH、WRH分别是构造流程标称的错误位置、原因和修复指导。在独立语义审定完成前，正文应说明这些是实验条件名称，而不是每条提示真实性的已验证结论。

CH提供的信息组合比某些误导条件丰富，提示具体程度也不匹配；缺少“长度/具体程度匹配但语义中性”的控制组。因此，现有比较衡量的是生成提示包之间的差异，不能完全分离内容真假、信息量和表述形式的效果。

## 三、先保证构念与评测有效性

### 3.1 提示构造审计：结构成立，语义结论仍有限

原始1,088条增强条件的实际首条用户消息均包含当前对应提示文本，未发现文本不匹配；ORIG没有假设块。之前的结构审计核验了272条错误位置文件/符号的存在性及提示生成一致性。这验证了刺激投放，但不验证提示被感知为可信或具有足够误导强度。[C02]

局部复算构造产物发现：[C02]

- 259/272（95.2%）WLH提示与存储的正确位置共享文件，主要操纵错误符号，而非错误文件。
- WRH只有7种修复正文，其中176/272（64.7%）为“在操作之前加入输入验证”。
- 构造过滤主要检验位置/类别/文本差异；不同类别不等于不同因果机制，不同修复文本也不等于无效修复。
- 对Astropy13033、Django13794、Django16454的既有检查提示原因重叠或新增函数邻近符号问题，CH也不能直接当作精确诊断的金标准。

重要含义：不显著结果可能来自真实抗干扰，也可能来自刺激较弱、同文件信息泄露或类别分离不足。当前数据不能在这些解释间给出确定答案。不能写“所有假设均通过语义有效性验证”，不能补造人工一致率。

### 3.2 原始提交完整性需要更正

| 条件 | 轨迹数 | 实际非空提交补丁 | 有评测标签 |
|---|---:|---:|---:|
| ORIG | 272 | 271 | 271 |
| CH | 272 | 271 | 271 |
| WLH | 272 | 272 | 272 |
| WCH | 272 | 271 | 271 |
| WRH | 272 | 271 | 271 |
| 总计 | 1,360 | 1,356 | 1,356 |

既有归一化导出记为1,359次提交，但3条TimeExceeded记录的原始submission和preds.json均为空：ORIG/CH的Django11734、WRH的Sphinx8621。因此“1,359次提交、只有WCH一次无补丁”的旧表述需要修改。4条缺失评测标签不能悄悄转为失败；可另列最保守结果处理，但必须统一说明。[C08]

`time_to_first_successful_edit_seconds`中的successful只指编辑工具调用未报错，不指修复正确或候选补丁已通过测试。旧稿“first viable/correct edit”“earlier commitment to a viable edit”应改为“first successfully executed edit”。`steps`来自事件序列，并非统一定义的修复迭代次数。

### 3.3 两类结果不一致必须分开

**不同评测分母。** Astropy7606在原始评测报告及新增两轮中，ORIG与增强条件对一个回归测试的检查不一致，涉及`test_compose_roundtrip[]`。新增两轮输入明确为ORIG240个PASS_TO_PASS、其余条件241个；增强条件该额外测试失败。同补丁出现ORIG成功、其他失败，不能用于证明假设致害。原始CH/WLH/WCH存储输入与实际报告也不完全一致，说明当前输入文件不能替代当时评测清单的证据。[C08]

**相同补丁、不同评测标签。** 原始Astropy7606和Sphinx8475，以及跨轮的Requests1724出现此现象。Sphinx与Requests相关元数据归一化后相同，失败涉及链接检查、HTTP验证/重定向等测试；当前只确认标签不一致，尚未确证全部根因，不能直接标为已证实的网络flakiness。[C08]

另外，Requests5414/Pylint8898有汇总歧义标记，Matplotlib23299有一次RateLimitError。五个其他任务出现空字符串测试项的增删，属于表示/清理差异，目前没有证据说明其改变实质评测分母，不应与Astropy问题等量齐观。Django10554/WRH报告没有完整测试列表，是补丁应用失败，不是已确认的测试配置变化。

新增敏感/稳定组都记录mini-swe-agent2.4.6、glm4.6和主要预算，但敏感组配置显式包含BigModel API地址，其他组未显式记录；没有运行期端点证据前，不应断言实际服务配置完全一致。

结论：主表可以报告“原始评测标签”，但最终论文必须附统一评测重检结果。基准通过率不是语义正确率，同补丁标签不一致也不是代理行为变化。

## 四、RQ1：提示条件如何影响最终修复结果？

### 4.1 全样本平均效果接近零，但不是等效证明

以下使用实际可用评测标签，配对比较取各条件与ORIG的共同任务。95%区间采用任务配对bootstrap，seed20261002，20,000次；p为精确McNemar，4项Holm校正。[C04]

| 条件 | 成功/有评测 | 成功率 | 配对任务 | 获益/受损任务 | 相对ORIG差值，pp（95%CI） | 校正p |
|---|---:|---:|---:|---:|---:|---:|
| ORIG | 207/271 | 76.38% | — | — | — | — |
| CH | 206/271 | 76.01% | 271 | 9/10 | -0.37 [-3.69,2.58] | 1.000 |
| WLH | 209/272 | 76.84% | 271 | 7/6 | +0.37 [-2.21,2.95] | 1.000 |
| WCH | 210/271 | 77.49% | 270 | 9/7 | +0.74 [-2.22,3.70] | 1.000 |
| WRH | 207/271 | 76.38% | 270 | 8/9 | -0.37 [-3.33,2.59] | 1.000 |

不是简单比较五个独立比例；配对关系降低了任务难度差异的干扰。所有差值区间含零，没有检出单轮平均结果变化。误导条件不呈现一致的负效应，CH也没有提高平均成功率。

区间可约束该配置、该任务集的一次执行平均变化，但未预先定义最小有意义差异、未进行正式等效研究，不能宣布“鲁棒性已得到证明”。更不能用“p=1”来说明提示没有被采用。

### 4.2 评测审计排除不会改变平均结果结论

作为探索性稳健性分析，统一排除6个存在实质评测/运行审计标记的任务：Astropy7606、Sphinx8475、Requests5414、Pylint8898、Requests1724、Matplotlib23299。最后两个的标记来自新增运行，因此这不是原始主实验预先注册的排除规则。[C04]

剩余266个任务的CH/WLH/WCH/WRH配对差为+0.38、+0.75、+0.76、-0.38pp，校正p仍均为1。另有更保守的11任务排除分析，将5个仅空测试项表示差异任务也去除，结果同样未显示平均效应。必须同时保留原始标签与排除分析，不能只报告更有利的一个。

**RQ1答案：** 当前生成提示包没有表现出可检出的平均修复率变化。结果是有边界的负结果，不是提示不影响行为、没有局部风险或真实误导天然无害的证据。

## 五、RQ2：平均结果接近时，修复过程发生什么变化？

### 5.1 补丁导出的指导减少部分搜索与执行工作

原始全任务配对差：[C05]

| CH − ORIG指标 | 配对n | 差值中位数 | 任务相对差中位数 | 秩双列效应量 | 每指标4比较Holm p | 全64比较Holm p |
|---|---:|---:|---:|---:|---:|---:|
| Runtime | 272 | -25.18秒 | -10.7% | -0.213 | .0095 | .140 |
| 首次执行成功的编辑 | 271 | -9.21秒 | -15.6% | -0.247 | .0017 | .0278 |
| 总token | 272 | -24,305 | -14.0% | -0.172 | .0505 | .763 |
| 事件步数 | 272 | -5 | -8.6% | -0.239 | .0030 | .0465 |
| 工具调用 | 272 | -3 | -7.9% | -0.241 | .0029 | .0460 |
| 搜索/读取 | 272 | -1 | -7.8% | -0.227 | .0074 | .111 |

与“正确提示提高成功率”的原始直觉不同，指导的较明确收益落在寻找编辑入口、工具交互成本，而不是已检测到的最终成功率变化。总token原始比较没有达到严格显著性，不能作为稳固的全样本token节省结论。

本次同时记录全部16指标×4条件的64项检验，保留按指标4项的原有校正，再提供全64项校正与精确符号检验作为稳健性对照。所有新增分析均为探索性，不将更容易显著的校正族事后包装成预先计划。

过程差分常有重尾、偏态或大量零。采用Wilcoxon并不自动解决差分对称性的要求，因此同时提供不依赖差分对称性的符号检验；不删除IQR标记的极值。全样本CH工具调用和首次编辑的方向差异在64项符号检验校正下也保留；部分幅度检验不保留。表中比较不是通用代理规律。

### 5.2 稳定组复核：成本变化更容易跨轮出现

两轮补充先按任务平均配对差，再在任务之间计算统计量。以下为排除Requests1724与限流任务后稳定组48个任务的结果；每群体7指标×4条件进行28项Holm校正。[C06]

| 条件差 | 指标 | 差值中位数 | 任务相对差中位数 | 秩双列效应量 | Wilcoxon校正p | 符号检验校正p |
|---|---|---:|---:|---:|---:|---:|
| CH − ORIG | 工具调用 | -6.75次 | -18.7% | -.614 | .0085 | .386 |
| CH − ORIG | 搜索/读取 | -2.75次 | -15.5% | -.610 | .0085 | .0150 |
| WRH − ORIG | 总token | -117,254.5 | -23.2% | -.621 | .0051 | .0194 |
| WRH − ORIG | 工具调用 | -4.75次 | -12.6% | -.610 | .0085 | .118 |

完整50任务结果与之方向一致，详见补充实验报告。CH搜索/读取下降和WRH token下降在更保守的方向检验下也保留，是当前较有说服力的过程证据。

说明：任务相对差中位数不是总体token消耗减少比例，也不能换算为美元；provider累计token含重复上下文，`recorded_cost=0`应视作费用不可用。稳定组由初始41成功与9失败任务分层构成，成本结果只能首先解释为这个样本上的观察。

敏感组本次过程比较在28项校正下没有显著结果。不能写“所有任务中假设都显著改变过程”。“WRH减少成本”也不能被解释为误导更好——减少探索可能是有效收缩，也可能是过早收敛，需要行为与语义证据区分。

### 5.3 误导的局部行为移位：保留为候选机制

原始WRH平均每任务少1次测试调用；272对中104对更少、68对更多、100对相同，差值中位数为0。每指标4比较校正p=.0038，全64比较p=.0579。错误修复条件的金标准文件精确度只在22个配对任务上改变，其中18下降、4上升；效应量-.672，每指标校正p=.0204，全64比较p=.296。[C05]

这些不是普遍性结果，且全局校正下不稳健。适合在次要分析中写成“集中于少数轨迹的验证/定位变化”，不能在摘要中作为已确立的主结论。文件重合与代码行文本重合仅是诊断；当前行重合实现不保留文件或语义位置，不能叫语义修复精度。

**RQ2答案：** 在当前配置与刺激上，部分指导条件改变搜索/工具成本，却没有可检出的平均成功率收益。正确指导的搜索收缩在稳定组复核；错误修复指导也可能缩短工作过程。是否损害证据搜集不能由成本单独决定。

## 六、RQ3：哪些条件差异可复现，哪些轨迹机制仍可信？

### 6.1 初始混合结果不是已确证的敏感性

原始269个完整任务中，34个在五条件下同时出现成功和失败，占12.6%。这只是单轮的“条件间结果混合率”，不是因误导发生失败的比例，也不是稳定上下文敏感性的总体流行率。[C03]

| 重复性指标 | 初始混合组34任务 | 初始稳定组50任务 |
|---|---:|---:|
| 两轮都复现首轮完整五位结果 | 3/34，8.8% | 40/50，80% |
| 三轮有同条件结果变化的任务 | 31/34，91.2% | 10/50，20% |
| 三轮变化的任务—条件单元 | 85/170，50% | 14/250，5.6% |
| 仅两轮补充，同条件不一致率 | 54/170，31.8% | 14/250，5.6% |
| 仅两轮补充，至少一条件变化任务 | 23/34 | 10/50 |
| 审计排除后同条件不一致率 | 48/150，32%（30任务） | 12/240，5%（48任务） |

最有力的对照使用仅新增两轮，避免定义群体的首轮直接进入验证指标。选定群体在重复运行上的稳定性明显不同，但两群体可能在难度、提示特征和服务配置上也不同，不能解释为误导造成了31.8%的失败概率。[C07]

混合组同条件跨轮不一致率31.8%，95%任务bootstrap区间[21.8,42.4]%；同轮跨条件不一致率36.5%，区间[28.8,43.8]%。二者差+4.7pp，区间[-5.9,14.7]。说明背景运行变异与条件差异同量级，但不能把两种比较相减作为纯粹的提示因果效果。

首轮63个相对ORIG的方向翻转任务—条件对中，仅11个在两轮补充都复现方向：5/31有益、6/32有害。它们不是63个独立任务，包含评测不一致任务，仅作为原始标签下的描述。[C07]

### 6.2 补充结果的条件效应仍不确定

| 群体 | ORIG | CH | WLH | WCH | WRH |
|---|---:|---:|---:|---:|---:|
| 初始混合组，两轮68运行/条件 | 48.5% | 55.9% | 57.4% | 42.6% | 39.7% |
| 初始稳定组，两轮100运行/条件 | 77% | 81% | 80% | 81% | 81% |
| 审计后混合组，两轮60运行/条件 | 46.7% | 58.3% | 63.3% | 45.0% | 43.3% |
| 审计后稳定组，两轮96运行/条件 | 79.2% | 82.3% | 81.3% | 82.3% | 83.3% |

推断的独立单元分别是34/50任务，不是68/100运行。以两轮任务平均差作精确符号翻转检验，原始8比较Holm校正p均为1。审计后所有未校正精确检验也未达到.05，WLH对比最小p=.087。不要根据离散数据的某个bootstrap区间不含零改变这一判断。也不能从选定样本给出全部272任务的两轮总体成功率。[C07]

### 6.3 定性机制：案例与重复性一起报告

以下三位串按首轮/补充轮1/补充轮2排列：[C09]

| 案例 | ORIG | CH | WLH | WCH | WRH | 当前适合的论证 |
|---|---|---|---|---|---|---|
| Django17084 | 111 | 111 | 111 | 111 | 000 | 最强的重复局部条件差异；进一步核查验证收缩与修复位置偏移 |
| SymPy20428 | 000 | 101 | 000 | 000 | 000 | 定位到上游表达式域可帮助，但CH不是保证 |
| scikit-learn14629 | 110 | 111 | 111 | 101 | 000 | WRH下重复错误子系统；ORIG/WCH也能走入失败分支 |
| SymPy13877 | 111 | 111 | 111 | 111 | 010 | WRH下路径可以改变，不是确定性有害 |
| Astropy13033 | 000 | 110 | 010 | 000 | 010 | 同文件语义边界与运行分支变化；“正确提示唯一成功”不再成立 |
| Pylint7080 | 000 | 000 | 001 | 100 | 100 | 初始误导成功未在新两轮复现，不能当作稳定获益 |
| Django14765 | 011 | 111 | 111 | 111 | 111 | 原始ORIG失败未复现，“提示帮助”的首轮解释需降级 |
| Astropy7606 | 111 | 000 | 000 | 000 | 000 | 有评测分母问题，不用作提示有害/恢复失败案例 |

**优先案例：Django17084。** 成功轨迹修改`django/db/models/sql/query.py`，WRH失败轨迹修改`django/db/models/aggregates.py`，三次结果保持分离。原始WRH轨迹第70/88条消息明确围绕在`Aggregate.resolve_expression`加入validation来组织修复，与输入验证提示相符。此证据支持“提示一致的局部修复路径”这一解释；尚不能证明内在心理锚定，不能断言它在明确反证之后仍坚持，除非人工定位反证及后续行为。[C09]

建议将六种旧机制收敛为四个可观察轨迹类别：

1. 上游定位/架构转向：以SymPy20428等解释访问与修改位置如何变化。
2. 局部修复坚持/子系统偏移：以Django17084、scikit-learn14629解释可重复局部失败。
3. 同位置语义近失：以Astropy13033解释文件正确与语义修复正确的区别。
4. 未稳定复现的搜索分支：以Pylint7080、Django14765解释单条轨迹“获益”不等于稳定条件作用。

评测分母/同补丁冲突独立放入方法审计，不能归入代理行为机制。每幅案例图须标任务、条件、轮次、关键提示、实际动作、证据、最终结果及三轮支持程度。图中不要画没有轨迹证据的“接受假设→遇到反证→恢复”节点。

三轮完全复现原始签名的3任务中，Astropy7606有评测问题，Django11964至少一次关键失败为空补丁超时。不能宣称“3个已验证的锚定案例”。

### 6.4 不应再报告未观察到的恢复率

当前没有独立、裁决后的initial adoption、contradiction encounter、revision/persistence标签。接收提示不是接受；访问文件不是采信；失败测试不一定反驳假设；错误条件下成功也不一定经过恢复。因此锚定率、反证遭遇率、恢复率和恢复时延均不具备可报告的可靠分子/分母。人工编码前，不从自动特征或结果反推这些状态。

作为探索性对照，初始混合任务中成功运行相对失败运行的任务内平均差中位数为+83.9秒、+14.8事件步、+7.3工具调用、+0.4测试调用。该比较按结果分组，不是随机干预，不能推断“多探索会造成成功”；可能受任务分支、运行预算及较早放弃影响。[C10]

**RQ3答案：** 首轮混合结果集中于重复运行较不稳定的任务，但具体条件签名复现弱。局部路径偏移可以重复，某些初始有益分支则未重复；恢复机制仍需直接过程标注。单轮任务结果不宜直接作为上下文易感性标签。

## 七、综合发现与可写进摘要的证据层级

| 发现 | 当前证据 | 推荐位置 | 必须避免的扩张 |
|---|---|---|---|
| 平均成功率变化小，未检出平均效应 | 272任务配对与审计排除分析 | 摘要、RQ1 | “证明等效/完全鲁棒” |
| CH较早进入实际编辑、减少工具交互 | 全样本过程检验；稳定组搜索复核 | 摘要、RQ2 | “正确诊断保证成功” |
| 错误修复条件也能减少成本 | 稳定组重复，审计排除与方向检验 | RQ2、Discussion | “误导提高效率/正确性” |
| 首轮混合任务具有较高重复变异 | 仅补充轮的31.8%对5.6%，排除后32%对5% | 核心RQ3、摘要 | “误导导致31.8%不稳定” |
| 少数路径偏移跨轮重复 | Django17084等位置与三轮结果 | 定性机制 | “所有失败都是锚定” |
| 评测不一致可伪造条件分离 | Astropy实际清单与同补丁标签 | Methods、稳健性 | “所有差异都是评测错误” |
| 代理经反证实现恢复 | 目前缺可靠标注 | 待补充 | 报告虚构恢复率/普遍恢复能力 |

不建议维持“最终结果鲁棒、过程高度敏感”的过强二分。更准确的是“未检出平均结果变化、若干过程指标改变、单任务差异需重复确认”。强过程机制也不能由成本检验自动推导。

## 八、面向 FSE 的新颖性与论证方式

### 8.1 现有主张与近期工作的重合

FSE2027官方征稿将原创性、贡献重要性、方法可靠性、评价、呈现与相关工作比较列为评审依据，并鼓励可复现研究。因此本报告优先解决证据与新颖性，而不是认为负结果不能发表。[FSE2027 Research Papers](https://conf.researchr.org/track/fse-2027/fse-2027-papers)

以下仅为针对最接近工作的核检，不是系统性文献综述；作者仍需阅读全文并确认最终定位。

| 已核对的工作 | 与本研究重合 | 本研究应争取的增量 |
|---|---|---|
| [On Randomness in Agentic Evals](https://arxiv.org/abs/2602.07150) | 单次代理评测有变异，推荐重复运行 | 具体诊断先验的跨条件作用与同条件变异分离，而不是重复证明“代理有随机性” |
| [Prompt-Induced Waste in Coding Agents](https://arxiv.org/abs/2608.01347) | 提示改变推理、验证与成本；涉及误导架构提示 | 在真实仓库缺陷上，将位置/原因/修复先验、直接证据与可重复局部路径系统关联；需要已审定刺激与行为证据 |
| [Evaluating AGENTS.md](https://arxiv.org/abs/2602.11988) | 上下文影响行为/成本，但未普遍提高成功率 | 针对缺陷诊断的真假先验，而非一般仓库上下文；区分局部收敛与反证后修正 |
| [Are “Solved Issues” in SWE-bench Really Solved Correctly?](https://software-lab.org/publications/icse2026_SWE-bench-correctness.pdf) | 测试通过不足以证明修复语义正确 | 将评测一致性作为提示干预效果的必要控制，不能声称首次发现SWE-bench评测问题 |
| [SWE-rebench](https://arxiv.org/abs/2505.20411) | 新任务与去污染评价 | 若要外推真实抗误导能力，增加较新任务复核，而非用项目识别说明污染 |

最接近的提示成本论文也讨论误导提示，并不只研究一般verbosity。只写“提示影响过程而非成功率”创新性不足。仅写“单轮评测不可靠”又会与已有更大规模研究重合。本研究的潜力是诊断先验与仓库证据的具体相互作用；当前这部分恰好是需要补强的部分。

### 8.2 推荐标题与贡献

推荐工作标题：

**Diagnostic Priors in Coding Agents: Repair Outcomes, Search Behavior, and Repeatability**

或更强调研究问题：

**Do Diagnostic Hypotheses Change Coding-Agent Repairs? A Repeatability-Aware Study**

暂时避免以“Recovery from Misleading Hypotheses”为中心标题，因为目前没有可靠恢复率与反证转向的系统证据。

可以主张的贡献：其一，真实任务上的提示条件配对实验及可审计轨迹数据；其二，针对首轮混合/稳定任务的重复性分析，展示任务标签对重复执行的敏感程度；其三，将过程成本、局部修复路径与评测一致性放入统一证据框架。候选机制分类作为探索性贡献，独立标注后再提升为主要机制结果。

这些贡献的原创性和影响力仍需与相关工作逐项比较；“构造了272任务”与“完成2,200次运行”是规模事实，不自动构成科学贡献。研究问题与代码字段也应对齐：协议中的旧RQ2/RQ3为锚定/恢复率，当前可报告版本已经不同，应明确记录分析计划的修订而不伪称原先预注册。

### 8.3 三个研究问题，机制保留在RQ3

**RQ1 — Repair outcomes.** What changes in evaluator-resolved outcomes are observed under patch-derived and potentially misleading diagnostic guidance?

**RQ2 — Search and validation behavior.** How do these context conditions change repository exploration, editing, testing, and resource consumption?

**RQ3 — Repeatability and local mechanisms.** Which outcome and trajectory patterns persist across repeated executions, and what repository-grounded evidence explains reproducible and non-reproducible cases?

语义审定后再将RQ1的potentially misleading改为validated misleading。原RQ4机制分析降为RQ3的定性子节，不追加模型/项目复杂度回归来凑独立RQ。

## 九、可改写为论文 Results 的英文内容

以下文字仅适用于当前原始标签与探索性审计分析，不宣称提交就绪。标记对应本目录`claim-evidence.json`，最终投稿前需人工复核并移出正文。

### RQ1 — Small average outcome differences do not establish robustness

We analyzed 1,360 initial executions of 272 tasks under five context conditions, followed by 840 additional executions of 84 outcome-stratified tasks. Four initial evaluator outcomes were unavailable. Across the initial sample, evaluator-resolved rates ranged from 76.01% to 77.49%. Paired differences relative to the original issue context ranged from −0.37 to +0.74 percentage points, and all paired bootstrap intervals included zero. Exact McNemar comparisons were non-significant after Holm correction. These results provide no detected average outcome effect in the studied configuration, but do not establish equivalence or resistance to semantically validated misinformation. [C01,C04]

### RQ2 — Context changes parts of the repair process

Patch-derived guidance changed parts of the search and editing process without a detected increase in resolution. Relative to the original context, CH reduced the median time to the first successfully executed edit by 9.21 seconds and the median tool-call count by three. Both differences survived correction across all 64 initial process comparisons. The edit-time metric measures successful execution of an editing action, not the production of a correct repair. Other reductions, including runtime and repository reads, were significant under the original per-metric correction but not under the broader correction. We therefore distinguish robust process findings from metric-family-dependent evidence. [C05]

The additional executions provided a complementary process check in the initially stable cohort. After excluding two audit-flagged tasks, CH reduced search/read calls by a median of 2.75, while WRH reduced total reported tokens by a median of 117,254.5. These comparisons survived both the 28-comparison Wilcoxon correction and corrected direction-only sign tests. Lower resource consumption, however, does not by itself imply better evidence use: a restricted search can be productive or prematurely convergent. [C06]

### RQ3 — Initial mixed outcomes rarely reproduce as an identical condition signature

Among 269 initially complete task blocks, 34 had mixed outcomes across conditions. Only three of these tasks reproduced the same five-condition signature in both subsequent rounds, compared with 40 of the 50 initially stable tasks. Comparing only the additional rounds, same-condition disagreement was 31.8% in the initially mixed cohort and 5.6% in the initially stable cohort. Following audit-based exclusions, the respective rates were 32.0% and 5.0%. Thus, initial between-condition disagreement identified a cohort with substantial repeat-execution variability, rather than establishing a reproducible prompt effect for every task. The outcome-stratified selection and configuration limitations restrict this observation to the studied cohorts. [C03,C07]

Within the initially mixed cohort, between-condition disagreement was 36.5%, only 4.7 percentage points above same-condition repeat disagreement; the task-bootstrap interval for this difference included zero. We use this comparison to contextualize variability, not to subtract away a causal noise component. Several initially beneficial condition-specific outcomes failed to recur, while a small number of local failure paths persisted. In Django17084, ORIG, CH, WLH, and WCH succeeded in all three executions, whereas WRH failed in all three and modified aggregate handling instead of SQL query construction. This pattern motivates a local path-displacement interpretation, but establishing anchoring after contradictory evidence requires independent trajectory coding. [C07,C09]

### Evaluation consistency is necessary for interpreting prompt effects

Our audit also identified outcome differences that cannot be attributed to agent behavior. For Astropy7606, augmented conditions checked an additional regression-test identifier that the original condition did not check. Identical submitted patches therefore received different labels across conditions. We also found identical-patch label conflicts in Sphinx8475 and Requests1724. We retain these observations as evaluator-consistency findings and report sensitivity analyses, rather than treating them as evidence of anchoring or recovery. Final effect estimates require reevaluation under a common verified test specification. [C08]

## 十、图表组织与篇幅建议

当前已生成三组PNG/PDF/SVG：

- `outcomes-and-repeatability`：原始配对成功率差、保守审计排除后差值、补充同条件不一致率。区间为任务bootstrap；不能凭图宣称等效。
- `process-paired-effects`：工具/搜索/测试的配对平均差与区间，包含全样本和保守排除对照。均值图不与中位数结果混写。
- `raw-process-distributions`：全样本分布诊断，保留极值，runtime/token采用对数轴，建议补充材料使用。

正文最优先保留：一个结果森林图、一个重复性任务热图或模式变化图、一个审计后案例轨迹图。表格保留数据完整性、核心配对指标、案例证据边界。17种首轮签名的完整表移入附录，因为它不再是最重要发现。

案例图每个箭头都必须有实际事件支撑。当前四机制PPT应根据新增重复结果修改说明，特别是Pylint7080和Astropy7606；本次没有直接修改旧图或稿件。

FSE2027官方主轨当前采用单栏acmsmall，初稿正文/图最多18页、参考文献4页；应按当前规则重新校准篇幅，而不是继续沿用通用双栏FSE旧模板。[FSE2027 submission instructions](https://conf.researchr.org/track/fse-2027/fse-2027-papers)

## 十一、最小补强路径与停止条件

### P0：无需新的模型生成，先重评已有补丁

统一每个任务所有条件/轮次的基础提交、测试补丁、F2P/P2P清单、镜像与解析器。先校正Astropy7606；对Sphinx8475和Requests1724相同补丁做重复评测，量化评测标签波动。Requests5414/Pylint8898核对歧义根因；将限流与超时/预算失败分开。修复提交识别导出问题并重新核验完整性表。

对于同一补丁，多次重评只增加评测观察，不能当成新的代理生成运行。公开原始标签、统一后的标签、变更原因和评测版本hash。不得只选择最有利的重评结果。

### P1：语义审定与直接机制证据

先独立审定用于机制分析和重复实验的84任务×4条件=336条增强提示；再完成其余提示或使用预先确定的代表性分层样本。逐条标“有效/无效/不确定”、可能替代有效修复、同文件泄露和隔离程度。审定时隐藏运行结果，避免因为某条件成功就宣布提示有效。

行为标注优先覆盖34任务的三轮误导轨迹：34×3条件×3轮=306条；还应加入稳定任务对照，避免从全部结果混合任务中估计总体锚定频率。复核提示后再标首次采信、矛盾证据、修订/坚持，给出事件定位、直接引文和裁决记录。若做总体频率，按抽样设计报告分母与权重；不伪造双评审、kappa或裁决过程。

### P2：扩展独立性，而非只加同一个模型的运行数

建议一个额外模型或代理配置对同一审定任务子集进行配对复核，固定环境与端点；如果主张跨模型，就必须有跨模型证据。再选择较新、非结果筛选的任务小集验证刺激与机制，具体样本量由预算与预先设定的最小有意义效果决定。新增刺激修正意味着新的实验版本，不能拿旧运行匹配新提示。

没有必要把“再重复到显著”为目标。每个条件仅3次执行仍难可靠估计单任务成功概率；优先追加有直接机制证据且无评测问题的局部案例，同时保留不利与反例。大规模复杂度/仓库回归、贝叶斯模型或更多漂亮图表，都不能解决无效刺激和未编码机制。

### 两条投稿路线

**机制路线（推荐，但需P0/P1及至少一项外部复核）。** 主贡献是诊断先验与仓库证据如何决定搜索/修复路径；重复性作为排除替代解释的设计；可保留恢复主题，但必须补出反证与转向的直接证据。

**评价方法路线（可利用当前数据，但创新性较难）。** 主贡献是提示干预研究应区分平均效果、重复运行变异和评测不一致，并提供可复现审计框架。现有随机性/评测质量文献强，若仅凭3个冲突任务和一个模型，贡献可能不够；需更系统的适用性验证，不宜保证FSE竞争力。

如果无法补齐P0，当前结论只能作为带明确警告的探索性报告。若P0完成但P1未完成，则不以“误导假设恢复机制”投稿；可保留过程与重复性研究，主动限制构念解释。

## 十二、最终可支持与不可支持的结论

可以支持：在本配置与任务集上未检出平均成功率变化；部分搜索与成本指标存在提示条件差异；初始结果混合任务的同条件重复变异较高；单次方向翻转多数未稳定复现；存在局部可重复失败路径和评测一致性问题。

目前不能支持：所有刺激真实有效；所有34任务因提示而敏感；代理普遍从误导恢复；误导普遍无害或稳定有益；成本更低说明推理更好；金标准行重合等于语义正确；现象可推广所有代理/模型/语言；10条项目识别诊断证明训练污染。

仓库来源诊断的10条样本全部识别项目，但没有非空PR编号，识别依据分布为5条explicit、5条technical_inference；它只能说明来源可推断，不能作为污染证据。该早期诊断不是新的修复实验，应放Threats而非主Results。[C11]

最终建议摘要中心句：

> In the studied configuration, diagnostic context changes parts of repository search without a detected average resolution benefit, while repeated executions show that initial mixed outcomes are an unreliable substitute for reproducible context sensitivity.

在P0/P1完成前，副标题与摘要不宣称具有普遍性的misleading-hypothesis robustness或recovery能力。现有素材具备形成严谨实证论文的基础；能否达到FSE所需重要性与新颖性，取决于对诊断—证据机制的补强，而非对负结果的修辞转换。

## 十三、可复现材料与方法工具说明

本目录`summary.json`包含原始/排除分析、全部过程统计、分布与极值诊断、提交/评测/构造审计、重复实验汇总；CSV保留所有检验而非只保留显著项。`source-manifest.json`与`claim-evidence.json`提供机器核检的来源与论断映射，人工verification状态未完成，不伪称提交就绪。原始逐轮记录仍见`analysis/repeated-runs-2026-10-02`。

复现脚本：`/Users/gzq/Repo/FSE2027/scripts/analyze_all_fse_results.py`。依赖NumPy2.3.5、SciPy1.18.1和已安装Matplotlib，实际版本保存在summary.json。固定seed20261002。统计技能提供了假设/效应量/多重比较与证据边界检查；绘图遵循Matplotlib技能导出矢量图。其流程参考已核对的[Kassis et al., Scientific Agent Skills (2026)](https://arxiv.org/abs/2609.00065)。该引用是分析辅助方法说明，不替代软件工程领域的相关工作或独立科学验证。

所有外部核检只发送公开论文/会议页面请求，没有上传本研究数据或未发表稿件。最终作者应独立确认数值、解释、参考文献与AI辅助披露要求。
