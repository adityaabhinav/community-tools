export const config = {
  thoughtSpotHost: "https://ps-internal.thoughtspot.cloud",

  // "Adi111's first Liveboard"
  liveboardId: "5a328046-8a29-4c11-ad85-52cfdf685005",

  // Each viz is embedded on its own so the right-click "Filter" action
  // (Action.CrossFilter) can be removed per viz. Set showFilter: true to keep it.
  // true = remove the right-click Filter (cross filter) action on every viz,
  // regardless of the rule below.
  hideCrossFilterEverywhere: true,

  // How to decide which vizzes keep the Filter action. Override in the URL with
  // ?rule=flag or ?rule=vizId.
  //   "flag"  - use each viz's showFilter below
  //   "vizId" - keep it only for the ids listed in filterVizIds
  filterRule: "flag",
  filterVizIds: ["76d43801-1362-4d0c-b555-dc34d04b59b7"],

  vizzes: [
    { id: "d1c75d6c-a4ce-410c-975c-3ee8d949fcda", title: "Total Sales Amt by Zip Code", showFilter: false },
    { id: "5b1ef104-6112-4cf9-ba02-96f40045706f", title: "Total sales by Monthly date", showFilter: false },
    { id: "61105548-452b-4cf6-b8e6-492c0d33453e", title: "Total quantity purchased by Monthly date", showFilter: false },
    { id: "76d43801-1362-4d0c-b555-dc34d04b59b7", title: "Viz 4", showFilter: true },
  ],
};
