export type BodyAreaMapSide = "front" | "back";

type SharedShape = {
  transform?: string;
};

export type BodyAreaRegionShape =
  | ({ type: "path"; d: string; fillRule?: "evenodd" | "nonzero"; clipRule?: "evenodd" | "nonzero" } & SharedShape)
  | ({ type: "ellipse"; cx: number; cy: number; rx: number; ry: number } & SharedShape)
  | ({ type: "rect"; x: number; y: number; width: number; height: number; rx?: number; ry?: number } & SharedShape);

export type BodyAreaRegion = {
  id: string;
  side: BodyAreaMapSide;
  label: string;
  aliases?: string[];
  shapes: BodyAreaRegionShape[];
};

export const BODY_AREA_SHORTCUTS = [
  { id: "shoulder", label: "Shoulder", value: "Shoulder", side: "front" as const },
  { id: "knee", label: "Knee", value: "Knee" },
  { id: "ankle-foot", label: "Ankle", value: "Ankle / foot" },
  { id: "lower-back", label: "Lower back", value: "Lower back", side: "back" as const },
  { id: "wrist-hand", label: "Wrist", value: "Wrist / hand" },
  { id: "hamstring", label: "Hamstring", value: "Hamstring", side: "back" as const },
] as const;

const FRONT_BODY_AREA_REGIONS: BodyAreaRegion[] = [
  {
    id: "front-head",
    side: "front",
    label: "Head",
    aliases: ["Head / Neck"],
    shapes: [{ type: "ellipse", cx: 130, cy: 44, rx: 29, ry: 32 }],
  },
  {
    id: "front-neck",
    side: "front",
    label: "Neck",
    aliases: ["Head / Neck"],
    shapes: [
      {
        type: "path",
        d: "M114 79 C118 72 123 68 130 68 C137 68 142 72 146 79 L144 101 C140 107 135 111 130 111 C125 111 120 107 116 101 Z",
      },
    ],
  },
  {
    id: "front-left-shoulder",
    side: "front",
    label: "Left shoulder",
    shapes: [
      {
        type: "path",
        d: "M108 98 C96 94 78 98 66 110 C57 120 52 136 58 149 C64 161 76 166 91 162 C102 158 110 149 114 137 C117 126 116 112 108 98 Z",
      },
    ],
  },
  {
    id: "front-right-shoulder",
    side: "front",
    label: "Right shoulder",
    shapes: [
      {
        type: "path",
        d: "M152 98 C164 94 182 98 194 110 C203 120 208 136 202 149 C196 161 184 166 169 162 C158 158 150 149 146 137 C143 126 144 112 152 98 Z",
      },
    ],
  },
  {
    id: "front-chest",
    side: "front",
    label: "Chest",
    shapes: [
      {
        type: "path",
        d: "M93 109 C103 98 116 93 130 93 C144 93 157 98 167 109 C173 124 174 145 170 163 C165 177 152 186 130 188 C108 186 95 177 90 163 C86 145 87 124 93 109 Z",
      },
    ],
  },
  {
    id: "front-abdomen",
    side: "front",
    label: "Abdomen",
    aliases: ["Core", "Stomach"],
    shapes: [
      {
        type: "path",
        d: "M101 184 C111 176 120 172 130 172 C140 172 149 176 159 184 C164 202 164 229 158 251 C151 267 142 276 130 278 C118 276 109 267 102 251 C96 229 96 202 101 184 Z",
      },
    ],
  },
  {
    id: "front-groin-hip",
    side: "front",
    label: "Groin / Hip front",
    aliases: ["Groin", "Hip front", "Hip"],
    shapes: [
      {
        type: "path",
        d: "M103 252 C111 246 121 243 130 243 C139 243 149 246 157 252 C162 266 161 286 154 299 C148 309 140 315 130 317 C120 315 112 309 106 299 C99 286 98 266 103 252 Z",
      },
    ],
  },
  {
    id: "front-left-upper-arm",
    side: "front",
    label: "Left upper arm",
    aliases: ["Left arm"],
    shapes: [{ type: "ellipse", cx: 75, cy: 190, rx: 16, ry: 45, transform: "rotate(14 75 190)" }],
  },
  {
    id: "front-right-upper-arm",
    side: "front",
    label: "Right upper arm",
    aliases: ["Right arm"],
    shapes: [{ type: "ellipse", cx: 185, cy: 190, rx: 16, ry: 45, transform: "rotate(-14 185 190)" }],
  },
  {
    id: "front-left-elbow",
    side: "front",
    label: "Left elbow",
    shapes: [{ type: "ellipse", cx: 67, cy: 245, rx: 13, ry: 17, transform: "rotate(12 67 245)" }],
  },
  {
    id: "front-right-elbow",
    side: "front",
    label: "Right elbow",
    shapes: [{ type: "ellipse", cx: 193, cy: 245, rx: 13, ry: 17, transform: "rotate(-12 193 245)" }],
  },
  {
    id: "front-left-forearm",
    side: "front",
    label: "Left forearm",
    aliases: ["Left lower arm"],
    shapes: [{ type: "ellipse", cx: 57, cy: 305, rx: 14, ry: 53, transform: "rotate(9 57 305)" }],
  },
  {
    id: "front-right-forearm",
    side: "front",
    label: "Right forearm",
    aliases: ["Right lower arm"],
    shapes: [{ type: "ellipse", cx: 203, cy: 305, rx: 14, ry: 53, transform: "rotate(-9 203 305)" }],
  },
  {
    id: "front-left-wrist-hand",
    side: "front",
    label: "Left wrist / hand",
    aliases: ["Left wrist", "Left hand"],
    shapes: [{ type: "ellipse", cx: 45, cy: 373, rx: 20, ry: 25, transform: "rotate(10 45 373)" }],
  },
  {
    id: "front-right-wrist-hand",
    side: "front",
    label: "Right wrist / hand",
    aliases: ["Right wrist", "Right hand"],
    shapes: [{ type: "ellipse", cx: 215, cy: 373, rx: 20, ry: 25, transform: "rotate(-10 215 373)" }],
  },
  {
    id: "front-left-quad",
    side: "front",
    label: "Left quad",
    aliases: ["Left thigh"],
    shapes: [{ type: "ellipse", cx: 112, cy: 388, rx: 22, ry: 65, transform: "rotate(4 112 388)" }],
  },
  {
    id: "front-right-quad",
    side: "front",
    label: "Right quad",
    aliases: ["Right thigh"],
    shapes: [{ type: "ellipse", cx: 148, cy: 388, rx: 22, ry: 65, transform: "rotate(-4 148 388)" }],
  },
  {
    id: "front-left-knee",
    side: "front",
    label: "Left knee",
    shapes: [{ type: "ellipse", cx: 112, cy: 463, rx: 18, ry: 23 }],
  },
  {
    id: "front-right-knee",
    side: "front",
    label: "Right knee",
    shapes: [{ type: "ellipse", cx: 148, cy: 463, rx: 18, ry: 23 }],
  },
  {
    id: "front-left-shin",
    side: "front",
    label: "Left shin",
    aliases: ["Left lower leg"],
    shapes: [{ type: "ellipse", cx: 112, cy: 523, rx: 18, ry: 49, transform: "rotate(2 112 523)" }],
  },
  {
    id: "front-right-shin",
    side: "front",
    label: "Right shin",
    aliases: ["Right lower leg"],
    shapes: [{ type: "ellipse", cx: 148, cy: 523, rx: 18, ry: 49, transform: "rotate(-2 148 523)" }],
  },
  {
    id: "front-left-ankle-foot",
    side: "front",
    label: "Left ankle / foot",
    aliases: ["Left ankle", "Left foot"],
    shapes: [
      {
        type: "path",
        d: "M95 546 C103 536 115 534 123 540 C129 545 129 555 122 562 C114 568 100 567 92 558 C88 553 90 549 95 546 Z",
      },
    ],
  },
  {
    id: "front-right-ankle-foot",
    side: "front",
    label: "Right ankle / foot",
    aliases: ["Right ankle", "Right foot"],
    shapes: [
      {
        type: "path",
        d: "M165 540 C173 534 185 536 193 546 C198 549 200 553 196 558 C188 567 174 568 166 562 C159 555 159 545 165 540 Z",
      },
    ],
  },
];

const BACK_BODY_AREA_REGIONS: BodyAreaRegion[] = [
  {
    id: "back-neck",
    side: "back",
    label: "Neck",
    aliases: ["Head / Neck"],
    shapes: [
      {
        type: "path",
        d: "M114 78 C118 71 123 67 130 67 C137 67 142 71 146 78 L146 107 C142 112 136 116 130 116 C124 116 118 112 114 107 Z",
      },
    ],
  },
  {
    id: "back-left-shoulder",
    side: "back",
    label: "Left shoulder",
    shapes: [
      {
        type: "path",
        d: "M108 100 C96 96 79 100 67 111 C58 121 53 136 59 149 C65 160 77 166 91 163 C102 160 109 151 113 139 C115 129 115 114 108 100 Z",
      },
    ],
  },
  {
    id: "back-right-shoulder",
    side: "back",
    label: "Right shoulder",
    shapes: [
      {
        type: "path",
        d: "M152 100 C164 96 181 100 193 111 C202 121 207 136 201 149 C195 160 183 166 169 163 C158 160 151 151 147 139 C145 129 145 114 152 100 Z",
      },
    ],
  },
  {
    id: "back-upper-back",
    side: "back",
    label: "Upper back",
    aliases: ["Upper spine"],
    shapes: [
      {
        type: "path",
        d: "M92 108 C102 97 116 92 130 92 C144 92 158 97 168 108 C173 124 173 148 168 171 C161 186 150 195 130 198 C110 195 99 186 92 171 C87 148 87 124 92 108 Z",
      },
    ],
  },
  {
    id: "back-lower-back",
    side: "back",
    label: "Lower back",
    aliases: ["Back", "Lumbar"],
    shapes: [
      {
        type: "path",
        d: "M101 194 C109 187 119 183 130 183 C141 183 151 187 159 194 C164 209 163 235 156 258 C149 272 141 280 130 282 C119 280 111 272 104 258 C97 235 96 209 101 194 Z",
      },
    ],
  },
  {
    id: "back-left-upper-arm",
    side: "back",
    label: "Left upper arm",
    aliases: ["Left arm"],
    shapes: [{ type: "ellipse", cx: 76, cy: 194, rx: 16, ry: 46, transform: "rotate(15 76 194)" }],
  },
  {
    id: "back-right-upper-arm",
    side: "back",
    label: "Right upper arm",
    aliases: ["Right arm"],
    shapes: [{ type: "ellipse", cx: 184, cy: 194, rx: 16, ry: 46, transform: "rotate(-15 184 194)" }],
  },
  {
    id: "back-left-elbow",
    side: "back",
    label: "Left elbow",
    shapes: [{ type: "ellipse", cx: 67, cy: 249, rx: 13, ry: 17, transform: "rotate(12 67 249)" }],
  },
  {
    id: "back-right-elbow",
    side: "back",
    label: "Right elbow",
    shapes: [{ type: "ellipse", cx: 193, cy: 249, rx: 13, ry: 17, transform: "rotate(-12 193 249)" }],
  },
  {
    id: "back-left-forearm",
    side: "back",
    label: "Left forearm",
    aliases: ["Left lower arm"],
    shapes: [{ type: "ellipse", cx: 56, cy: 309, rx: 14, ry: 53, transform: "rotate(10 56 309)" }],
  },
  {
    id: "back-right-forearm",
    side: "back",
    label: "Right forearm",
    aliases: ["Right lower arm"],
    shapes: [{ type: "ellipse", cx: 204, cy: 309, rx: 14, ry: 53, transform: "rotate(-10 204 309)" }],
  },
  {
    id: "back-left-wrist-hand",
    side: "back",
    label: "Left wrist / hand",
    aliases: ["Left wrist", "Left hand"],
    shapes: [{ type: "ellipse", cx: 45, cy: 377, rx: 20, ry: 25, transform: "rotate(10 45 377)" }],
  },
  {
    id: "back-right-wrist-hand",
    side: "back",
    label: "Right wrist / hand",
    aliases: ["Right wrist", "Right hand"],
    shapes: [{ type: "ellipse", cx: 215, cy: 377, rx: 20, ry: 25, transform: "rotate(-10 215 377)" }],
  },
  {
    id: "back-glutes",
    side: "back",
    label: "Glutes",
    aliases: ["Glute", "Hip back"],
    shapes: [
      {
        type: "path",
        d: "M100 273 C109 266 119 263 130 263 C141 263 151 266 160 273 C165 287 165 312 157 328 C149 339 111 339 103 328 C95 312 95 287 100 273 Z",
      },
    ],
  },
  {
    id: "back-left-hamstring",
    side: "back",
    label: "Left hamstring",
    aliases: ["Left thigh"],
    shapes: [{ type: "ellipse", cx: 112, cy: 388, rx: 21, ry: 65, transform: "rotate(4 112 388)" }],
  },
  {
    id: "back-right-hamstring",
    side: "back",
    label: "Right hamstring",
    aliases: ["Right thigh"],
    shapes: [{ type: "ellipse", cx: 148, cy: 388, rx: 21, ry: 65, transform: "rotate(-4 148 388)" }],
  },
  {
    id: "back-left-calf",
    side: "back",
    label: "Left calf",
    aliases: ["Left lower leg"],
    shapes: [{ type: "ellipse", cx: 112, cy: 503, rx: 18, ry: 55, transform: "rotate(2 112 503)" }],
  },
  {
    id: "back-right-calf",
    side: "back",
    label: "Right calf",
    aliases: ["Right lower leg"],
    shapes: [{ type: "ellipse", cx: 148, cy: 503, rx: 18, ry: 55, transform: "rotate(-2 148 503)" }],
  },
  {
    id: "back-left-ankle-foot",
    side: "back",
    label: "Left ankle / foot",
    aliases: ["Left ankle", "Left foot"],
    shapes: [
      {
        type: "path",
        d: "M96 545 C104 538 115 537 122 542 C128 548 127 558 120 564 C111 569 99 568 92 560 C88 554 90 549 96 545 Z",
      },
    ],
  },
  {
    id: "back-right-ankle-foot",
    side: "back",
    label: "Right ankle / foot",
    aliases: ["Right ankle", "Right foot"],
    shapes: [
      {
        type: "path",
        d: "M164 542 C171 537 182 538 190 545 C196 549 198 554 194 560 C187 568 175 569 166 564 C159 558 158 548 164 542 Z",
      },
    ],
  },
];

export const BODY_AREA_REGIONS: Record<BodyAreaMapSide, BodyAreaRegion[]> = {
  front: FRONT_BODY_AREA_REGIONS,
  back: BACK_BODY_AREA_REGIONS,
};

const BODY_AREA_REGION_LOOKUP = [...FRONT_BODY_AREA_REGIONS, ...BACK_BODY_AREA_REGIONS].flatMap((region) => {
  const aliases = [region.label, ...(region.aliases ?? [])];
  return aliases.map((alias) => [normalizeBodyAreaLabel(alias), region] as const);
});

export function normalizeBodyAreaLabel(value: string) {
  return value
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/[^\w]+/g, " ")
    .trim();
}

export function findBodyAreaRegion(value: string, preferredSide?: BodyAreaMapSide) {
  const normalized = normalizeBodyAreaLabel(value);
  if (!normalized) {
    return null;
  }

  if (preferredSide) {
    const preferredMatch = BODY_AREA_REGIONS[preferredSide].find((region) =>
      [region.label, ...(region.aliases ?? [])].some((alias) => normalizeBodyAreaLabel(alias) === normalized),
    );
    if (preferredMatch) {
      return preferredMatch;
    }
  }

  const match = BODY_AREA_REGION_LOOKUP.find(([alias]) => alias === normalized);
  return match?.[1] ?? null;
}
