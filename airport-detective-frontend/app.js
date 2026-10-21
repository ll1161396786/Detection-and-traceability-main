const clips = [
  {
    id: "0740",
    label: "0740 片段",
    title: "0740 片段 / 随身包绑定无情况",
    video: "./public/media/0740-preview.mp4",
    poster: "./public/media/frames/0740_01.jpg",
    eventLabel: "无情况",
    level: "clear",
    object: {
      id: "ROI-OBJ-11",
      name: "黑色随身包 / 左侧前排乘客膝前",
      summary: "系统将 P-01 与膝前黑色随身包建立绑定，后续仅出现短时遮挡复核，未超过 10 秒阈值，判定无情况。",
      preview: "./public/media/enhanced/items/0740-v2.png",
      previewFallback: "./public/media/crops/item/0740.jpg",
      risk: "低",
      stay: "4秒",
      confidence: "88%",
      review: "无情况"
    },
    actions: [
      "将 ROI-OBJ-11 归档为正常随身物样本。",
      "保留短时遮挡复核片段，不推送站台安保。",
      "继续用于 10 秒阈值规则的无情况对照演示。"
    ],
    ownerTrace: {
      mode: "clear",
      ownerId: "P-01",
      title: "已闭环：随身包持续归属 P-01",
      time: "07:42:53",
      image: "./public/media/frames/0740_05.jpg",
      stageId: "verified",
      button: "查看闭环帧",
      description: "ROI-OBJ-11 始终保持在 P-01 的随身区域内，短时遮挡后重新确认绑定，不进入失主追踪流程。",
      signals: ["持续邻近", "遮挡解除", "无情况"]
    },
    binding: {
      personId: "P-01",
      personName: "左侧前排黑衣乘客",
      objectId: "ROI-OBJ-11",
      objectName: "黑色随身包",
      threshold: 10,
      state: "clear",
      separatedSeconds: 4,
      summary: "P-01 与 ROI-OBJ-11 建立随身物绑定，短时遮挡造成 4 秒复核窗口，未超过 10 秒阈值。"
    },
    engine: {
      persons: 14,
      luggage: 4,
      associations: 4,
      pending: 0,
      upload: "3段样例已接入",
      vlm: "3/3 语义复核",
      search: "Top-3 92%",
      review: "无待复核"
    },
    candidates: [
      {
        id: "P-01",
        name: "左侧前排黑衣乘客",
        score: 88,
        risk: "低",
        tags: ["持续邻近", "绑定未断开", "无情况"],
        note: "黑色随身包始终位于其膝前与手部可达区域，遮挡解除后绑定关系继续成立。"
      },
      {
        id: "P-02",
        name: "左侧粉衣乘客",
        score: 24,
        risk: "低",
        tags: ["同排邻近", "无拿取动作"],
        note: "与目标物处于同侧座位区域，但没有形成拿取、放置或持续绑定证据。"
      },
      {
        id: "P-03",
        name: "中部过道乘客",
        score: 16,
        risk: "低",
        tags: ["路径经过", "排除"],
        note: "仅在过道中经过，行动轨迹与左侧随身包位置没有持续关联。"
      }
    ],
    stages: [
      {
        id: "bound",
        from: 0,
        to: 20,
        time: "07:42:19",
        title: "乘客与随身包建立绑定",
        status: "人-物检测 / 绑定建立",
        description: "系统框选左侧前排 P-01，并识别其膝前黑色随身包 ROI-OBJ-11，建立一对一随身物绑定。",
        bindingState: "bound",
        separatedSeconds: 0,
        bindingTitle: "P-01 与 ROI-OBJ-11 已绑定",
        bindingDescription: "人和包保持同一区域稳定接触，脱离计时为 0 秒，不进入告警判断。",
        scores: ["0.90", "0.88", "0.87"],
        overlays: [
          { type: "person", label: "P-01 左侧前排", x: 7.8, y: 38.0, w: 18.3, h: 57.5 },
          { type: "object linked", label: "ROI-OBJ-11 随身包", x: 13.5, y: 75.5, w: 10.2, h: 18.2 },
          { type: "path linked", label: "随身绑定区", x: 6.5, y: 41.0, w: 20.5, h: 54.0 }
        ]
      },
      {
        id: "review",
        from: 20,
        to: 34,
        time: "07:42:42",
        title: "短时遮挡复核，未触发",
        status: "接触断开 / 10秒内观察",
        description: "前景乘客与扶手造成短时遮挡，系统只进入 4 秒复核窗口；目标仍在 P-01 随身区域内。",
        bindingState: "grace",
        separatedSeconds: 4,
        bindingTitle: "遮挡 4 秒，未触发预警",
        bindingDescription: "复核计时未超过 10 秒，且目标没有离开绑定区域，因此不生成遗留物事件。",
        scores: ["0.88", "0.74", "0.82"],
        overlays: [
          { type: "person", label: "P-01 绑定保持", x: 7.8, y: 38.0, w: 18.3, h: 57.5 },
          { type: "object watch", label: "ROI-OBJ-11 复核中", x: 13.5, y: 75.5, w: 10.2, h: 18.2 },
          { type: "path watch", label: "4s 观察窗", x: 6.5, y: 41.0, w: 20.5, h: 54.0 }
        ]
      },
      {
        id: "verified",
        from: 34,
        to: 45,
        time: "07:42:53",
        title: "绑定恢复确认，无情况",
        status: "无情况 / 绑定闭环",
        description: "遮挡解除后 ROI-OBJ-11 仍与 P-01 保持随身绑定，未出现超过 10 秒的无人接触状态。",
        bindingState: "clear",
        separatedSeconds: 4,
        bindingTitle: "4 秒内确认绑定，无预警",
        bindingDescription: "系统确认该目标是 P-01 的随身物，事件闭环为无情况样本。",
        scores: ["0.92", "0.86", "0.89"],
        overlays: [
          { type: "person clear", label: "P-01 归属确认", x: 7.8, y: 38.0, w: 18.3, h: 57.5 },
          { type: "object clear", label: "ROI-OBJ-11 已闭环", x: 13.5, y: 75.5, w: 10.2, h: 18.2 },
          { type: "path clear", label: "无情况闭环", x: 6.5, y: 41.0, w: 20.5, h: 54.0 }
        ]
      }
    ]
  },
  {
    id: "0750",
    label: "0750 片段",
    title: "0750 片段 / 随身袋遗留告警",
    video: "./public/media/0750-demo.mp4",
    poster: "./public/media/frames/demo_510.jpg",
    eventLabel: "有情况",
    level: "danger",
    object: {
      id: "ROI-OBJ-18",
      name: "浅色随身袋 / 右侧过道座位前",
      summary: "P-04 带入浅色随身袋并在右侧过道座位前留下，断开接触超过 10 秒仍无人拿走，系统标记为有情况。",
      preview: "./public/media/enhanced/items/0750-v2.png",
      previewFallback: "./public/media/crops/item/0750.jpg",
      risk: "高",
      stay: "90秒+",
      confidence: "91%",
      review: "人工待确认"
    },
    actions: [
      "锁定 07:58:09 带入帧与 08:00:09 告警帧。",
      "推送 P-04 匿名轨迹至站台安保复核。",
      "保持 ROI-OBJ-18 周边隔离，等待人工或排爆流程确认。"
    ],
    ownerTrace: {
      mode: "danger",
      ownerId: "P-04",
      title: "疑似失主：P-04 最早携带帧",
      time: "07:58:09",
      image: "./public/media/frames/demo_450.jpg",
      stageId: "bound",
      button: "定位带入帧",
      description: "从遗留物位置反向追踪，P-04 是最早与 ROI-OBJ-18 同时出现并形成携带关系的乘客，可作为疑似失主优先复核。",
      signals: ["最早携带", "最后接触", "离开后静止"]
    },
    binding: {
      personId: "P-04",
      personName: "中部携袋乘客",
      objectId: "ROI-OBJ-18",
      objectName: "浅色随身袋",
      threshold: 10,
      state: "alert",
      separatedSeconds: 90,
      summary: "P-04 入车厢时与 ROI-OBJ-18 建立绑定，断开接触后持续超过 90 秒无人重新接触，超过阈值触发预警。"
    },
    engine: {
      persons: 18,
      luggage: 5,
      associations: 4,
      pending: 1,
      upload: "3段样例已接入",
      vlm: "5/5 语义复核",
      search: "Top-1 91%",
      review: "1件断联超时"
    },
    candidates: [
      {
        id: "P-04",
        name: "中部携袋乘客",
        score: 91,
        risk: "高",
        tags: ["最后接触", "离开后静止", "疑似原持有人"],
        note: "在 07:58:09 与浅色随身袋同时进入画面，后续物品留在右侧过道座位前且无人拿走。"
      },
      {
        id: "P-07",
        name: "右侧座位乘客",
        score: 29,
        risk: "低",
        tags: ["空间邻近", "无接触"],
        note: "靠近物品停留区域，但没有出现放置、拿取或持续绑定动作。"
      },
      {
        id: "P-10",
        name: "左侧座位乘客",
        score: 17,
        risk: "低",
        tags: ["距离较远", "排除"],
        note: "与目标物位置距离较远，轨迹不支持原持有人判断。"
      }
    ],
    stages: [
      {
        id: "bound",
        from: 0,
        to: 30,
        time: "07:58:09",
        title: "乘客带入随身袋并绑定",
        status: "人-物检测 / 绑定建立",
        description: "P-04 与浅色随身袋同时进入画面，系统仅框选该乘客、随身袋和绑定区域，建立一对一关系。",
        bindingState: "bound",
        separatedSeconds: 0,
        bindingTitle: "P-04 与 ROI-OBJ-18 已绑定",
        bindingDescription: "人和随身物保持接触，目标归属明确，当前不进入遗留物预警。",
        scores: ["0.92", "0.86", "0.88"],
        overlays: [
          { type: "person", label: "P-04 携袋乘客", x: 39.0, y: 22.0, w: 13.8, h: 73.0 },
          { type: "object linked", label: "ROI-OBJ-18 携带袋", x: 45.2, y: 40.2, w: 8.2, h: 41.0 },
          { type: "path linked", label: "带入绑定区", x: 38.2, y: 34.0, w: 17.2, h: 59.0 }
        ]
      },
      {
        id: "separated",
        from: 30,
        to: 90,
        time: "07:58:39",
        title: "随身袋落地，开始计时",
        status: "接触断开 / 10秒内观察",
        description: "ROI-OBJ-18 留在右侧过道座位前，P-04 已离开绑定区域；当前断开接触 6 秒，仍处于观察窗内。",
        bindingState: "grace",
        separatedSeconds: 6,
        bindingTitle: "脱离 6 秒，未触发预警",
        bindingDescription: "10 秒内属于短时离物观察，系统只保留计时和空间半径证据。",
        scores: ["0.93", "0.78", "0.84"],
        overlays: [
          { type: "object watch", label: "ROI-OBJ-18 6s", x: 56.5, y: 78.0, w: 6.3, h: 19.0 },
          { type: "path watch", label: "10s 观察窗", x: 53.8, y: 73.8, w: 11.3, h: 24.2 }
        ]
      },
      {
        id: "alert",
        from: 90,
        to: 120,
        time: "07:59:39",
        title: "超过 10 秒，预警成立",
        status: "超过10秒 / 预警成立",
        description: "ROI-OBJ-18 断开接触超过 60 秒仍停留在地面，未被任何乘客拿走，系统转入有情况预警。",
        bindingState: "alert",
        separatedSeconds: 60,
        bindingTitle: "脱离 60 秒，触发预警",
        bindingDescription: "超过 10 秒仍无人重新接触，系统将原绑定关系转入失主回溯和人工复核流程。",
        scores: ["0.95", "0.88", "0.89"],
        overlays: [
          { type: "object alert", label: "ROI-OBJ-18 超时", x: 56.8, y: 78.5, w: 6.1, h: 20.0 },
          { type: "path alert", label: "静止告警区", x: 54.0, y: 74.0, w: 11.2, h: 24.5 }
        ]
      },
      {
        id: "situation",
        from: 120,
        to: 130,
        time: "08:00:09",
        title: "有情况：遗留物告警",
        status: "有情况 / 待人工复核",
        description: "ROI-OBJ-18 断开接触 90 秒后仍未被拿走，系统确认超过 10 秒阈值并回溯 P-04 带入帧。",
        bindingState: "alert",
        separatedSeconds: 90,
        bindingTitle: "脱离 90 秒，持续告警",
        bindingDescription: "预警已成立，系统回溯绑定源头，将 P-04 作为疑似失主优先展示。",
        scores: ["0.96", "0.91", "0.90"],
        overlays: [
          { type: "object alert", label: "ROI-OBJ-18 有情况", x: 56.8, y: 78.5, w: 6.1, h: 20.0 },
          { type: "path alert", label: "无人接触区域", x: 54.0, y: 74.0, w: 11.2, h: 24.5 }
        ]
      }
    ]
  },
  {
    id: "0800",
    label: "0800 片段",
    title: "0800 片段 / 脚边购物袋无情况",
    video: "./public/media/0800-preview.mp4",
    poster: "./public/media/frames/0800_01.jpg",
    eventLabel: "无情况",
    level: "clear",
    object: {
      id: "ROI-OBJ-26",
      name: "红色购物袋 / 右侧黄衣乘客脚边",
      summary: "系统将 P-06 与脚边红色购物袋建立绑定，物品始终留在乘客腿侧随身区域，未超过 10 秒阈值，判定无情况。",
      preview: "./public/media/enhanced/items/0800-v2.png",
      previewFallback: "./public/media/crops/item/0800.jpg",
      risk: "低",
      stay: "5秒",
      confidence: "86%",
      review: "无情况"
    },
    actions: [
      "将 ROI-OBJ-26 归档为正常脚边随身物样本。",
      "保留 5 秒复核片段，不触发车站安保处置流程。",
      "继续作为 10 秒阈值规则的无情况对照。"
    ],
    ownerTrace: {
      mode: "clear",
      ownerId: "P-06",
      title: "已闭环：购物袋持续归属 P-06",
      time: "08:02:32",
      image: "./public/media/frames/0800_04.jpg",
      stageId: "verified",
      button: "查看闭环帧",
      description: "ROI-OBJ-26 始终位于 P-06 腿侧和脚边范围内，短时复核后绑定关系继续成立，系统记录为无情况样本。",
      signals: ["持续邻近", "绑定未断开", "无情况"]
    },
    binding: {
      personId: "P-06",
      personName: "右侧黄色上衣乘客",
      objectId: "ROI-OBJ-26",
      objectName: "红色购物袋",
      threshold: 10,
      state: "clear",
      separatedSeconds: 5,
      summary: "P-06 与 ROI-OBJ-26 建立绑定，物品仅短时进入 5 秒复核窗口，未达到 10 秒预警阈值。"
    },
    engine: {
      persons: 16,
      luggage: 4,
      associations: 4,
      pending: 0,
      upload: "3段样例已接入",
      vlm: "4/4 语义复核",
      search: "Top-2 86%",
      review: "无待复核"
    },
    candidates: [
      {
        id: "P-06",
        name: "右侧黄色上衣乘客",
        score: 86,
        risk: "低",
        tags: ["持续邻近", "绑定未断开", "无情况"],
        note: "红色购物袋始终位于其腿侧和脚边，未出现离开车厢或无人接触超时。"
      },
      {
        id: "P-09",
        name: "右侧白衣乘客",
        score: 23,
        risk: "低",
        tags: ["空间邻近", "无接触"],
        note: "与目标处于同侧座位区域，但没有形成拿取、放置或持续绑定证据。"
      },
      {
        id: "P-13",
        name: "中部过道乘客",
        score: 15,
        risk: "低",
        tags: ["路径经过", "排除"],
        note: "仅在过道短时出现，行动轨迹与红色购物袋位置没有持续关联。"
      }
    ],
    stages: [
      {
        id: "bound",
        from: 0,
        to: 22.5,
        time: "08:01:58",
        title: "黄衣乘客与购物袋绑定",
        status: "人-物检测 / 绑定建立",
        description: "系统框选右侧座位 P-06 与脚边红色购物袋 ROI-OBJ-26，建立稳定随身物绑定。",
        bindingState: "bound",
        separatedSeconds: 0,
        bindingTitle: "P-06 与 ROI-OBJ-26 已绑定",
        bindingDescription: "购物袋位于乘客腿侧和脚边范围，脱离计时为 0 秒，不进入告警判断。",
        scores: ["0.89", "0.82", "0.84"],
        overlays: [
          { type: "person", label: "P-06 黄衣乘客", x: 72.5, y: 42.0, w: 19.0, h: 53.0 },
          { type: "object linked", label: "ROI-OBJ-26 购物袋", x: 74.8, y: 75.0, w: 10.8, h: 22.0 },
          { type: "path linked", label: "脚边绑定区", x: 72.0, y: 43.5, w: 21.0, h: 53.0 }
        ]
      },
      {
        id: "review",
        from: 22.5,
        to: 33.75,
        time: "08:02:21",
        title: "脚边短时复核，未触发",
        status: "接触断开 / 10秒内观察",
        description: "ROI-OBJ-26 保持在 P-06 脚边，系统仅进入 5 秒复核窗口；乘客仍未离开绑定区域。",
        bindingState: "grace",
        separatedSeconds: 5,
        bindingTitle: "脱离 5 秒，未触发预警",
        bindingDescription: "复核计时未超过 10 秒，且目标仍在乘客随身范围内，因此不生成遗留物事件。",
        scores: ["0.90", "0.78", "0.83"],
        overlays: [
          { type: "person", label: "P-06 绑定保持", x: 72.5, y: 42.0, w: 19.0, h: 53.0 },
          { type: "object watch", label: "ROI-OBJ-26 5s", x: 74.8, y: 75.0, w: 10.8, h: 22.0 },
          { type: "path watch", label: "5s 复核区", x: 72.0, y: 43.5, w: 21.0, h: 53.0 }
        ]
      },
      {
        id: "verified",
        from: 33.75,
        to: 45,
        time: "08:02:32",
        title: "绑定持续确认，无情况",
        status: "无情况 / 绑定闭环",
        description: "ROI-OBJ-26 持续位于 P-06 脚边随身区域，未出现超过 10 秒无人接触状态，判定无情况。",
        bindingState: "clear",
        separatedSeconds: 5,
        bindingTitle: "5 秒内确认绑定，无预警",
        bindingDescription: "系统确认该目标仍属于 P-06 随身物，事件闭环为无情况样本。",
        scores: ["0.92", "0.86", "0.88"],
        overlays: [
          { type: "person clear", label: "P-06 归属确认", x: 72.5, y: 42.0, w: 19.0, h: 53.0 },
          { type: "object clear", label: "ROI-OBJ-26 已闭环", x: 74.8, y: 75.0, w: 10.8, h: 22.0 },
          { type: "path clear", label: "无情况闭环", x: 72.0, y: 43.5, w: 21.0, h: 53.0 }
        ]
      }
    ]
  }
];

const toast = document.querySelector("#toast");
const itemList = document.querySelector("#itemList");
const itemCount = document.querySelector("#itemCount");
const videoGrid = document.querySelector("#videoGrid");
const wallStatus = document.querySelector("#wallStatus");
const hazardGrid = document.querySelector("#hazardGrid");
const hazardCount = document.querySelector("#hazardCount");
const luggageGrid = document.querySelector("#luggageGrid");
const luggageCount = document.querySelector("#luggageCount");
const behaviorList = document.querySelector("#behaviorList");
const behaviorCount = document.querySelector("#behaviorCount");
const tripList = document.querySelector("#tripList");
const tripCount = document.querySelector("#tripCount");
const trainNo = document.querySelector("#trainNo");
const trainMeta = document.querySelector("#trainMeta");
const trainRoute = document.querySelector("#trainRoute");

// 四路摄像头视频流（主画面 + 实时缩略图，持续循环播放）
const cameras = [
  { id: 1, video: "./public/media/0740-preview.mp4", poster: "./public/media/frames/0740_01.jpg" },
  { id: 2, video: "./public/media/0750-preview.mp4", poster: "./public/media/frames/0750_01.jpg" },
  { id: 3, video: "./public/media/0800-preview.mp4", poster: "./public/media/frames/0800_01.jpg" },
  { id: 4, video: "./public/media/0750-demo.mp4", poster: "./public/media/frames/demo_510.jpg" }
];

let activeCameraId = cameras[0].id;

// 车次列表：新加坡樟宜机场接驳车班次（按接驳航班编排，非高铁车次）
// 每辆车均接入自己的后端四路检测；历史 clipId 仅供旧演示代码兼容。
const trips = [
  {
    id: "T-04",
    no: "接驳车 04",
    full: "樟宜机场接驳车 04",
    depart: "07:40",
    flight: "SQ 118",
    route: "樟宜机场 T1 → T3 航站楼（SIN）",
    status: "已发车",
    statusClass: "",
    clipId: "0740"
  },
  {
    id: "T-05",
    no: "接驳车 05",
    full: "樟宜机场接驳车 05",
    depart: "07:50",
    flight: "SQ 12",
    route: "樟宜机场 T1 → T3 航站楼（SIN）",
    status: "运行中",
    statusClass: "running",
    clipId: "0750"
  },
  {
    id: "T-06",
    no: "接驳车 06",
    full: "樟宜机场接驳车 06",
    depart: "08:00",
    flight: "SQ 826",
    route: "樟宜机场 T1 → T3 航站楼（SIN）",
    status: "检票中",
    statusClass: "boarding",
    clipId: "0800"
  },
  {
    id: "T-07",
    no: "接驳车 07",
    full: "樟宜机场接驳车 07",
    depart: "08:10",
    flight: "SQ 916",
    route: "樟宜机场 T2 → T3 航站楼（SIN）",
    status: "待发车",
    statusClass: "",
    clipId: null
  },
  {
    id: "T-08",
    no: "接驳车 08",
    full: "樟宜机场接驳车 08",
    depart: "08:20",
    flight: "SQ 308",
    route: "樟宜机场 T2 → T3 航站楼（SIN）",
    status: "待发车",
    statusClass: "",
    clipId: null
  }
];

// Keep the existing initial selection (04); every vehicle uses backend inference.
for (const number of ["01", "02", "03"]) {
  trips.push({ id: `T-${number}`, no: `接驳车 ${number}`, full: `樟宜机场接驳车 ${number}`,
    depart: "—", flight: "—", route: "本地四路视频", status: "待检测", statusClass: "", clipId: null });
}

// 常见危险物（依据《中国民用航空安全检查规则》禁止携带和托运物品目录，作提示警示展示）
const hazardItems = [
  { name: "枪支武器", en: "Firearms", risk: "高", image: "./public/media/hazards/gun-white.png", note: "枪支、仿真枪及主要零部件" },
  { name: "爆炸物品", en: "Explosives", risk: "高", image: "./public/media/hazards/explosive-white.png", note: "弹药、爆破器材、烟花爆竹" },
  { name: "管制刀具", en: "Knives", risk: "中", image: "./public/media/hazards/knife-white.png", note: "匕首、弹簧刀、三棱刀等管制器具" },
  { name: "易燃液体", en: "Flammable", risk: "高", image: "./public/media/hazards/flammable-white.png", note: "汽油、酒精、油漆及含易燃溶剂制品" },
  { name: "腐蚀性物品", en: "Corrosive", risk: "中", image: "./public/media/hazards/corrosive-white.png", note: "硫酸、盐酸、烧碱等" },
  { name: "毒害品", en: "Toxic", risk: "高", image: "./public/media/hazards/toxic-white.png", note: "氰化物、砒霜、剧毒农药等" }
];

// 常见行李资料库：白底产品图，与危险物品库保持一致的目录卡片规格。
const luggageItems = [
  { name: "拉杆箱", en: "Suitcase", image: "./public/media/luggage/large-suitcase-v1.png", note: "大号硬壳万向轮拉杆箱" },
  { name: "登机箱", en: "Carry-on", image: "./public/media/luggage/cabin-suitcase-v1.png", note: "小型硬壳随身登机箱" },
  { name: "旅行背包", en: "Backpack", image: "./public/media/luggage/travel-backpack-v1.png", note: "双肩旅行与通勤背包" },
  { name: "旅行包", en: "Duffel", image: "./public/media/luggage/duffel-bag-v1.png", note: "软质手提旅行包" },
  { name: "手提袋", en: "Tote", image: "./public/media/luggage/canvas-tote-v1.png", note: "帆布日常手提袋" },
  { name: "公文包", en: "Briefcase", image: "./public/media/luggage/briefcase-v1.png", note: "商务文件与电脑公文包" }
];

// 行为证据截图（按行为类型分组）
// 截图选取原则：每一类行为的证据帧彼此独立、且不复用本界面其他模块（摄像头封面 / 遗留物缩略图 / 所属人头像）的同一帧，
// 避免同一张画面在多处出现导致「看起来是同一件事」；cam 标注取证来源摄像头，seq 为该类行为内的证据序号。
const behaviors = [
  {
    type: "剧烈运动",
    en: "Running",
    risk: "高",
    count: 3,
    issues: [
      { label: "追逐冲突", count: 2 },
      { label: "奔跑推搡", count: 1 }
    ],
    shots: [
      { src: "./public/media/frames/0750_02.jpg", cam: "C2", seq: 1 },
      { src: "./public/media/frames/demo_540.jpg", cam: "C4", seq: 2 }
    ]
  },
  {
    type: "长时间停留",
    en: "Loitering",
    risk: "中",
    count: 2,
    issues: [{ label: "连接处滞留", count: 2 }],
    shots: [{ src: "./public/media/frames/0800_05.jpg", cam: "C3", seq: 1 }]
  },
  {
    type: "人员聚集",
    en: "Gathering",
    risk: "中",
    count: 4,
    issues: [
      { label: "过道聚集", count: 3 },
      { label: "座位区围观", count: 1 }
    ],
    shots: [
      { src: "./public/media/frames/0740_04.jpg", cam: "C1", seq: 1 },
      { src: "./public/media/frames/0750_05.jpg", cam: "C2", seq: 2 }
    ]
  },
  {
    type: "打架斗殴",
    en: "Fighting",
    risk: "高",
    count: 1,
    issues: [{ label: "肢体冲突", count: 1 }],
    shots: [{ src: "./public/media/frames/0750_04.jpg", cam: "C2", seq: 1 }]
  }
];

// 风险等级 → 样式类名映射
const riskClass = { 高: "danger", 中: "warn", 低: "clear" };

// 候选所属人增强图（与 clips.candidates 的 id 一一对应）。
// PNG 使用纯白背景并保留头部至腰部的人物形象；原始裁剪图作为加载失败时的回退证据。
const candidateImages = {
  "P-01": { src: "./public/media/enhanced/owners/P-01-v2.png", fallback: "./public/media/crops/owner/P-01.jpg" },
  "P-02": { src: "./public/media/enhanced/owners/P-02-v2.png", fallback: "./public/media/crops/owner/P-02.jpg" },
  "P-03": { src: "./public/media/enhanced/owners/P-03-v2.png", fallback: "./public/media/crops/owner/P-03.jpg" },
  "P-04": { src: "./public/media/enhanced/owners/P-04-v2.png", fallback: "./public/media/crops/owner/P-04.jpg" },
  "P-06": { src: "./public/media/enhanced/owners/P-06-v2.png", fallback: "./public/media/crops/owner/P-06.jpg" },
  "P-07": { src: "./public/media/enhanced/owners/P-07-v2.png", fallback: "./public/media/crops/owner/P-07.jpg" },
  "P-09": { src: "./public/media/enhanced/owners/P-09-v2.png", fallback: "./public/media/crops/owner/P-09.jpg" },
  "P-10": { src: "./public/media/enhanced/owners/P-10-v2.png", fallback: "./public/media/crops/owner/P-10.jpg" },
  "P-13": { src: "./public/media/enhanced/owners/P-13-v2.png", fallback: "./public/media/crops/owner/P-13.jpg" }
};

let activeClip = clips[1];
// 默认选中04；切车时同步切换该车的预测画面和警报档案。
let activeTrip = trips[0];
function renderVideoWall() {
  if (isLiveTrip(activeTrip)) return renderLiveVideoWall();
  wallStatus.textContent = `${cameras.length}/4 在线`;
  const activeCamera = cameras.find((cam) => cam.id === activeCameraId) || cameras[0];
  const thumbnails = cameras
    .map((cam) => {
      const isActive = cam.id === activeCamera.id;
      return `
        <button
          class="camera-thumb ${isActive ? "active" : ""}"
          type="button"
          data-camera="${cam.id}"
          aria-label="在主窗口显示摄像头 ${cam.id}"
          aria-pressed="${isActive}"
          title="切换到摄像头 ${cam.id}"
        >
          <video
            class="cam-video camera-thumb-video"
            src="${cam.video}"
            poster="${cam.poster}"
            muted
            loop
            playsinline
            autoplay
            aria-hidden="true"
            tabindex="-1"
          ></video>
          <span class="camera-thumb-shade" aria-hidden="true"></span>
          <span class="camera-thumb-live" aria-hidden="true"><i class="live-dot"></i>实时</span>
          <span class="camera-thumb-label">摄像头 ${cam.id}</span>
        </button>
      `;
    })
    .join("");

  videoGrid.innerHTML = `
    <figure class="cam-cell cam-main" data-cam="${activeCamera.id}">
      <video
        class="cam-video"
        id="mainCameraVideo"
        data-camera="${activeCamera.id}"
        src="${activeCamera.video}"
        poster="${activeCamera.poster}"
        muted
        loop
        playsinline
        autoplay
      ></video>
      <div class="cam-shade"></div>
      <span class="cam-live"><i class="live-dot" aria-hidden="true"></i>实时</span>
      <span class="cam-badge" id="mainCameraBadge">摄像头 ${activeCamera.id}</span>
    </figure>
    <div class="camera-strip" role="group" aria-label="四路实时摄像头选择">
      ${thumbnails}
    </div>
  `;

  playAllCameras();
}

function selectCamera(cameraId) {
  if (isLiveTrip(activeTrip)) return selectLiveCamera(cameraId);
  const camera = cameras.find((item) => item.id === cameraId);
  if (!camera) return;

  const mainVideo = videoGrid.querySelector("#mainCameraVideo");
  const mainCell = videoGrid.querySelector(".cam-main");
  const mainBadge = videoGrid.querySelector("#mainCameraBadge");
  const selectedThumbVideo = videoGrid.querySelector(`[data-camera="${camera.id}"] .camera-thumb-video`);
  if (!mainVideo || !mainCell || !mainBadge) return;

  const resumeAt = Number.isFinite(selectedThumbVideo?.currentTime)
    ? selectedThumbVideo.currentTime
    : 0;

  activeCameraId = camera.id;
  videoGrid.querySelectorAll(".camera-thumb").forEach((thumb) => {
    const isActive = Number(thumb.dataset.camera) === activeCameraId;
    thumb.classList.toggle("active", isActive);
    thumb.setAttribute("aria-pressed", String(isActive));
  });

  if (Number(mainVideo.dataset.camera) === camera.id) return;

  mainCell.dataset.cam = String(camera.id);
  mainVideo.dataset.camera = String(camera.id);
  mainBadge.textContent = `摄像头 ${camera.id}`;
  mainVideo.onloadedmetadata = () => {
    const duration = Number.isFinite(mainVideo.duration) ? mainVideo.duration : resumeAt;
    mainVideo.currentTime = Math.min(resumeAt, duration);
    mainVideo.play().catch(() => {});
  };
  mainVideo.poster = camera.poster;
  mainVideo.src = camera.video;
  mainVideo.load();
}

function playAllCameras() {
  videoGrid.querySelectorAll(".cam-video").forEach((camVideo) => {
    camVideo.play().catch(() => {});
  });
}

// 车次列表「遗留物判定」列：取所属片段的检测结论，未接入检测片段的车次显示未检测
// 注意：这里只读取片段数据做列展示，不涉及右侧遗留物清单的选中态
function buildRadarSvg(trip) {
  const clip = trip.clipId ? clips.find((item) => item.id === trip.clipId) : null;
  if (!clip) return "";

  const score = (clip.candidates?.[0]?.score ?? 0) / 100;
  const sep = Math.min((clip.binding?.separatedSeconds ?? 0) / 10, 1);
  const riskMap = { 高: 1, 中: 0.5, 低: 0 };
  const riskVal = riskMap[clip.object?.risk] ?? 0;
  const persons = Math.min((clip.engine?.persons ?? 0) / 20, 1);

  const vals = [score, sep, riskVal, persons];
  const cx = 26, cy = 26, R = 22;
  const angles = [-Math.PI / 2, 0, Math.PI / 2, Math.PI];
  const pts = angles.map((a, i) => {
    const r = vals[i] * R;
    return `${(cx + r * Math.cos(a)).toFixed(2)},${(cy + r * Math.sin(a)).toFixed(2)}`;
  });
  const poly = pts.join(" ");

  const colorMap = { 高: "255,107,107", 中: "255,200,87", 低: "114,216,151" };
  const c = colorMap[clip.object?.risk] || "180,180,180";

  const outerPts = angles.map((a, i) => `${(cx + R * Math.cos(a)).toFixed(2)},${(cy + R * Math.sin(a)).toFixed(2)}`).join(" ");
  const innerPts = angles.map((a, i) => `${(cx + R / 2 * Math.cos(a)).toFixed(2)},${(cy + R / 2 * Math.sin(a)).toFixed(2)}`).join(" ");
  const axisLines = angles.map((a) => `<line x1="${cx}" y1="${cy}" x2="${(cx + R * Math.cos(a)).toFixed(2)}" y2="${(cy + R * Math.sin(a)).toFixed(2)}" stroke="rgba(255,255,255,0.12)" stroke-width="0.5"/>`).join("");
  const dotCircles = pts.map((p) => {
    const [px, py] = p.split(",");
    return `<circle cx="${px}" cy="${py}" r="2" fill="rgba(${c},1)"/>`;
  }).join("");

  return `<svg viewBox="0 0 52 52" width="52" height="52" aria-hidden="true" style="display:block">
    <polygon points="${outerPts}" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>
    <polygon points="${innerPts}" fill="none" stroke="rgba(255,255,255,0.05)" stroke-width="0.5"/>
    ${axisLines}
    <polygon points="${poly}" fill="rgba(${c},0.25)" stroke="rgba(${c},0.7)" stroke-width="1.2"/>
    ${dotCircles}
  </svg>`;
}

function buildBehaviorRadarSvg(item) {
  // 四个维度：发生频率、持续时间、影响范围、严重程度
  const riskMap = { 高: 1, 中: 0.5, 低: 0 };
  const riskVal = riskMap[item.risk] ?? 0;
  const freq = Math.min(item.count / 10, 1);                    // 发生频率
  const duration = Math.min(item.issues.reduce((sum, i) => sum + i.count, 0) / 10, 1); // 持续时间
  const spread = Math.min(item.shots.length / 5, 1);            // 影响范围
  const severity = riskVal;                                      // 严重程度

  const vals = [freq, duration, spread, severity];
  const cx = 26, cy = 26, R = 22;
  const angles = [-Math.PI / 2, 0, Math.PI / 2, Math.PI];
  const pts = angles.map((a, i) => {
    const r = vals[i] * R;
    return `${(cx + r * Math.cos(a)).toFixed(2)},${(cy + r * Math.sin(a)).toFixed(2)}`;
  });
  const poly = pts.join(" ");

  const colorMap = { 高: "255,107,107", 中: "255,200,87", 低: "114,216,151" };
  const c = colorMap[item.risk] || "180,180,180";

  const outerPts = angles.map((a, i) => `${(cx + R * Math.cos(a)).toFixed(2)},${(cy + R * Math.sin(a)).toFixed(2)}`).join(" ");
  const innerPts = angles.map((a, i) => `${(cx + R / 2 * Math.cos(a)).toFixed(2)},${(cy + R / 2 * Math.sin(a)).toFixed(2)}`).join(" ");
  const axisLines = angles.map((a) => `<line x1="${cx}" y1="${cy}" x2="${(cx + R * Math.cos(a)).toFixed(2)}" y2="${(cy + R * Math.sin(a)).toFixed(2)}" stroke="rgba(255,255,255,0.12)" stroke-width="0.5"/>`).join("");
  const dotCircles = pts.map((p) => {
    const [px, py] = p.split(",");
    return `<circle cx="${px}" cy="${py}" r="2" fill="rgba(${c},1)"/>`;
  }).join("");

  return `<svg viewBox="0 0 52 52" width="52" height="52" aria-hidden="true" style="display:block">
    <polygon points="${outerPts}" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>
    <polygon points="${innerPts}" fill="none" stroke="rgba(255,255,255,0.05)" stroke-width="0.5"/>
    ${axisLines}
    <polygon points="${poly}" fill="rgba(${c},0.25)" stroke="rgba(${c},0.7)" stroke-width="1.2"/>
    ${dotCircles}
  </svg>`;
}

function resolveTripVerdict(trip) {
  if (isLiveTrip(trip)) return liveTripVerdict(trip);
  const clip = trip.clipId ? clips.find((item) => item.id === trip.clipId) : null;
  if (!clip) return { label: "未检测", className: "" };
  return { label: clip.eventLabel, className: clip.level === "danger" ? "danger" : "clear" };
}

// 视频墙顶部车次条：跟随车次列表的选中车次更新
function renderCurrentTrip() {
  if (!activeTrip) return;
  trainNo.textContent = activeTrip.full;
  trainMeta.textContent = `接驳航班 ${activeTrip.flight} · ${activeTrip.depart} 发车`;
  trainRoute.textContent = activeTrip.route;
}

// 切车不自动启停检测，控制操作进行时禁止切车。
function selectTrip(id) {
  const trip = trips.find((item) => item.id === id);
  if (!trip) return;

  if (liveControlBusy || liveClearBusy) {
    showToast("正在处理检测操作，请稍后切换车辆。");
    return;
  }

  activeTrip = trip;
  activateLiveTrip();
  renderCurrentTrip();
  renderTrips();
  renderVideoWall();
  renderItemsAndPersons();
  showToast(`已切换到 ${trip.full}：接驳航班 ${trip.flight} · ${trip.depart} 发车`);
}

function renderTrips() {
  tripCount.textContent = `${trips.length} 个车次`;

  tripList.innerHTML = trips
    .map((trip) => {
      const clip = isLiveTrip(trip) ? liveTripClip(trip) : trip.clipId ? clips.find((item) => item.id === trip.clipId) : null;
      const verdict = resolveTripVerdict(trip);
      const isActive = activeTrip && activeTrip.id === trip.id;
      const rowClass = ["trip-row", isActive ? "active" : ""]
        .filter(Boolean)
        .join(" ");

      return `
        <button
          class="${rowClass}"
          type="button"
          data-trip="${trip.id}"
          title="${escapeHtml(`${trip.full} · ${trip.route} · ${liveStates.get(trip.id)?.configuration_error || '独立四路视频检测'}`)}"
        >
          <div class="trip-main">
            <div class="trip-no">
              <strong>${escapeHtml(trip.no)}</strong>
              <em>${escapeHtml(trip.id)}</em>
            </div>
            <span class="trip-route">${escapeHtml(`${trip.flight} · ${trip.route}`)}</span>
          </div>
          <span class="trip-tag trip-risk ${riskClass[clip?.object.risk] || ''}">${clip?.object.risk ?? '—'}</span>
          <span class="trip-radar">${isLiveTrip(trip) ? '<span class="dash">—</span>' : clip ? buildRadarSvg(trip) : '<span class="dash">—</span>'}</span>
          <span class="trip-firstitem">
            ${clip ? `<img src="${clip.object.preview}" data-fallback-src="${clip.object.previewFallback}" alt="${clip.object.id}" loading="lazy" />` : '<span class="dash">—</span>'}
          </span>
          <span class="trip-depart">${escapeHtml(trip.depart)}</span>
          <span class="trip-tag ${trip.statusClass}">${escapeHtml(trip.status)}</span>
          <span class="trip-tag ${verdict.className}">${escapeHtml(verdict.label)}</span>
        </button>
      `;
    })
    .join("");

  syncTripScrollHint();
  requestAnimationFrame(syncTripScrollHint);
}

function renderItemsAndPersons() {
  if (isLiveTrip(activeTrip)) return renderLiveItems();
  delete itemList.dataset.live;
  itemCount.textContent = `${clips.length} 件遗留物`;

  itemList.innerHTML = clips
    .map((clip) => {
      const object = clip.object;
      const active = clip.id === activeClip.id ? "active" : "";
      const owners = clip.candidates.slice(0, 3);

      const ownerCards = owners
        .map((owner) => {
          const image = candidateImages[owner.id] || { src: clip.ownerTrace.image, fallback: clip.ownerTrace.image };
          return `
            <div class="owner-card ${owner.risk === "高" ? "danger" : ""}" title="${escapeHtml(owner.note)}">
              <img class="owner-avatar" src="${image.src}" data-fallback-src="${image.fallback}" alt="${owner.id} 可能所属人照片" loading="lazy" tabindex="0" role="button" aria-haspopup="dialog" title="点击放大照片" />
              <div class="owner-body">
                <div class="owner-top">
                  <strong>${owner.id}</strong>
                  <span class="owner-score">${owner.score}%</span>
                </div>
                <span class="owner-name">${escapeHtml(owner.name)}</span>
              </div>
            </div>
          `;
        })
        .join("");

      return `
        <button class="item-row ${clip.level} ${active}" data-clip="${clip.id}" type="button">
          <div class="item-identity">
            <img class="item-thumb" src="${object.preview}" data-fallback-src="${object.previewFallback}" alt="${object.id} 预览" loading="lazy" tabindex="0" role="button" aria-haspopup="dialog" title="点击放大照片" />
            <div class="item-meta">
              <div class="item-title">
                <strong>${object.id}</strong>
                <span class="row-flag ${clip.level}">${clip.eventLabel}</span>
              </div>
              <p class="item-name">${escapeHtml(object.name)}</p>
              <span class="row-sub">风险 ${object.risk} · 置信度 ${object.confidence}</span>
            </div>
          </div>
          <div class="owner-list">${ownerCards}</div>
        </button>
      `;
    })
    .join("");
}

function renderCatalogCards(items) {
  return items
    .map(
      (item) => `
        <article class="catalog-card" role="listitem" title="${escapeHtml(item.note)}">
          <img class="catalog-image" src="${item.image}" alt="${escapeHtml(item.name)}" loading="lazy" />
          <div class="catalog-card-text">
            <span class="catalog-card-name">${escapeHtml(item.name)}</span>
            <span class="catalog-card-en">${escapeHtml(item.en)}</span>
          </div>
        </article>
      `
    )
    .join("");
}

function renderHazards() {
  hazardCount.textContent = `${hazardItems.length} 类`;
  luggageCount.textContent = `${luggageItems.length} 类`;
  hazardGrid.innerHTML = renderCatalogCards(hazardItems);
  luggageGrid.innerHTML = renderCatalogCards(luggageItems);
}

// 列表是否还有未露出的行：用于底部淡出提示 + 滚动到最后一行时取消提示
function syncScrollHint(list) {
  if (!list) return;
  const remaining = list.scrollHeight - list.scrollTop - list.clientHeight;
  list.classList.toggle("has-more", remaining > 4);
}

function syncBehaviorScrollHint() {
  syncScrollHint(behaviorList);
}

function syncTripScrollHint() {
  syncScrollHint(tripList);
}

function renderBehaviors() {
  behaviorCount.textContent = `${behaviors.length} 类`;

  behaviorList.innerHTML = behaviors
    .map((item) => {
      const issues = item.issues
        .map(
          (issue) => `
            <span class="issue"><b>${issue.count}</b> ${escapeHtml(issue.label)}</span>
          `
        )
        .join("");

      // 证据截图：固定尺寸缩略图（16:9），张数不同也不拉伸、不撑破卡片
      const shots = item.shots
        .map(
          (shot, index) => `
            <figure class="shot" title="${escapeHtml(`${item.type} · 摄像头 ${shot.cam} · 证据帧 ${index + 1}`)}">
              <img
                class="shot-image"
                src="${shot.src}"
                alt="${escapeHtml(item.type)} 证据截图 ${index + 1}"
                loading="lazy"
              />
              <figcaption class="shot-tag">
                <span class="shot-cam">${escapeHtml(shot.cam)}</span>
                <span class="shot-seq">${String(shot.seq).padStart(2, "0")}</span>
              </figcaption>
            </figure>
          `
        )
        .join("");

      return `
        <article class="behavior-item" data-shots="${item.shots.length}">
          <div class="behavior-info">
            <header class="behavior-head">
              <div class="behavior-title">
                <strong>${escapeHtml(item.type)}</strong>
                <span class="behavior-en">${escapeHtml(item.en)}</span>
              </div>
            </header>
            <div class="behavior-issues">${issues}</div>
          </div>
          <div class="behavior-shots" aria-label="${escapeHtml(item.type)} 证据截图 ${item.shots.length} 张">
            ${shots}
          </div>
          <div class="behavior-metrics">
            <span class="behavior-count"><strong>${item.count}</strong> 次</span>
            <span class="behavior-risk risk-tag ${riskClass[item.risk] || ''}">${item.risk}</span>
            <span class="behavior-radar">${buildBehaviorRadarSvg(item)}</span>
          </div>
        </article>
      `;
    })
    .join("");

  syncBehaviorScrollHint();
  requestAnimationFrame(syncBehaviorScrollHint);
}

function setClip(id) {
  const next = clips.find((clip) => clip.id === id);
  if (!next) return;
  activeClip = next;
  renderItemsAndPersons();
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2800);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => {
    const entities = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
    return entities[char];
  });
}

// 增强素材若因部署缓存或文件缺失加载失败，则无闪断地回退到原始监控裁剪图。
document.addEventListener(
  "error",
  (event) => {
    const image = event.target.closest?.("img[data-fallback-src]");
    if (!image) return;

    const fallback = image.dataset.fallbackSrc;
    delete image.dataset.fallbackSrc;
    if (fallback) image.src = fallback;
  },
  true
);

itemList.addEventListener("click", (event) => {
  const button = event.target.closest("[data-clip]");
  if (button) setClip(button.dataset.clip);
});

// 车次列表切换当前车辆及其四路画面、遗留物档案。
tripList.addEventListener("click", (event) => {
  const row = event.target.closest("[data-trip]");
  if (row) selectTrip(row.dataset.trip);
});

videoGrid.addEventListener("click", (event) => {
  const button = event.target.closest("[data-camera]");
  if (button) selectCamera(Number(button.dataset.camera));
});

renderVideoWall();
renderTrips();
renderCurrentTrip();
renderItemsAndPersons();
renderHazards();
renderBehaviors();
initializeLiveMonitor();
behaviorList.addEventListener("scroll", syncBehaviorScrollHint, { passive: true });
tripList.addEventListener("scroll", syncTripScrollHint, { passive: true });
window.addEventListener("resize", () => {
  syncBehaviorScrollHint();
  syncTripScrollHint();
});
