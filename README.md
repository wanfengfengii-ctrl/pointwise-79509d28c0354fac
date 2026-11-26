# 河桥社区环线运营服务

值班员导入当天的有序停靠表，把冻结修订装到车辆，再向站务发布。乘客请求指定本趟的下车任次。驾驶员依实际下一站报到，完成行程后收车，值班员按趟查阅原确认与实到的对账记录。

## 运行

使用 Python 3.11 标准库。在项目根目录分别开启两端。

```sh
python3 -B -m onboard.http --db vehicle.sqlite --port 8091
python3 -B -m dispatch.http --db dispatch.sqlite --port 8090 --vehicle http://127.0.0.1:8091
```

两端只监听 `127.0.0.1`，各用独立 SQLite 文件。调度启动时读取 `samples/`，只补缺失的站点和修订。使用 `--no-seed` 可跳过补种。默认样例线路为 `river`，修订 `R1` 依次停靠 `E1` 河桥东口和 `E2` 河桥西口，两处均播报为「河桥」。`R-WALK` 会先停靠 `A` 社区中心。

## JSON HTTP 接口

各入口接受 `POST`，正文为 JSON 对象。标识均为非空字符串。下表中的字段为必填，除非另有说明。业务结果为 JSON 对象。错误正文为 `{"error":"错误码","detail":"说明"}`。格式错误为 400，查无记录为 404，状态或原参冲突为 409，重复任次和未知站点为 422。

| 服务 | 路径 | 正文字段 | 结果 |
| --- | --- | --- | --- |
| 调度 | `/define_route` | `line, revision, calls` | `route` 为冻结表 |
| 调度 | `/open_trip` | `trip, vehicle, line, revision` | `status` 为 `opened` 或 `pending`，已开时返回初始 `route` 和 `next_stop` |
| 调度 | `/route_status` | `trip`，可选 `request` 为改道号 | 当前 `route` 及可选的 `diversion` 回执 |
| 调度 | `/divert_trip` | `trip, revision, request` | 当前 `route` 和此改道的 `diversion` 回执 |
| 车端 | `/confirm_stop` | `trip, occurrence, request` | 原确认及原 `speech`，无实播时该字段为空 |
| 车端 | `/confirmation_status` | `trip, request` | 读取已经受理的原确认 |
| 车端 | `/vehicle_status` | `trip` | 执行 `route`、`next_stop`、`arrivals`、`speeches`、`commitments` 和收车状态 |
| 车端 | `/arrive` | `trip, occurrence` | 本次 `arrival` 与 `next_stop` |
| 车端 | `/end_trip` | `trip` | 收车状态及实到件数 |
| 车端 | `/read_review` | `trip` | 按实际到站顺序保存的正式复盘 |

`calls` 按行车方向排列，每项包含 `occurrence` 和 `station`。允许空表。冻结表为每项附上 `name` 及从零开始的 `position`。同一修订号在同一线路内只接受同参重投。改道修订从开趟线路中选取。同一个任次及地点可以在未来后缀中换位。已经实际到过的前缀须保持。

本机样例开趟及确认如下。

```sh
curl -sS -H 'Content-Type: application/json' -d '{"trip":"T","vehicle":"bus-1","line":"river","revision":"R1"}' http://127.0.0.1:8090/open_trip
curl -sS -H 'Content-Type: application/json' -d '{"trip":"T","occurrence":"E1","request":"C1"}' http://127.0.0.1:8091/confirm_stop
curl -sS -H 'Content-Type: application/json' -d '{"trip":"T","occurrence":"E1"}' http://127.0.0.1:8091/arrive
```

趟号绑定车辆和初始修订。开趟失答时用原参续办。确认号和改道号各自在本趟内定参。确认状态为 `queued`、`spoken` 或 `terminated`。车端把可读取的实播事件视为实际语音确认，同次提交落实对应承诺。复领原实播不会补播。实际到达同一任次和地点时，驾驶记录关联该任次的全部待兑承诺。错误到站及提前收车保留原进度。

改道状态为 `pending`、`effective` 或 `conflict`。待查时站务仍见最后确认的版本。可用 `/route_status` 查本地回执，或用原参重投 `/divert_trip` 续查车端结局。每趟逐项结清改道，同趟上一项待查时新号返回 `diversion_pending`。未兑现的实播承诺保护对应停靠。车端按实际执行表办理乘客确认和到站，其他可执行任次可以继续办理。趟内已删停靠的旧确认即使稍后重新出现同一任次也维持原结局。`/internal/load_trip` 和 `/internal/divert_trip` 是两个本机服务之间的交件入口。

收车需要实际走完现行计划表。收车和正式复盘一同固化，重开后可继续按趟复领。复盘中每条承诺保留其确认号、原实播和实际到站。同次实到的多条兑现按原实播序列排列。没有实播承诺的趟返回零件数及空承诺列。

## 回归与演示

```sh
python3 -B check_project.py
python3 -B -m unittest -v tests.test_review.TestReview.test_day_of_service
```

`check_project.py` 由运行平台物化。完整 unittest 套件也可直接用 `python3 -B -m unittest discover -s tests -t . -v` 运行。演示在临时目录启动两端并实际发送 HTTP，跑完自定义排线、开趟、逆序确认、带已走前缀的改道、实到、收车和重开复领。`POINTWISE_SCENARIO` 行在业务断言后列出本次计算与下游记录。测试使用本机 HTTP 转发控制确定的请求和回包切点。
