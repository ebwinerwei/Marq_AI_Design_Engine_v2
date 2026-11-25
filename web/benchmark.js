export function evaluate(m){
 const pct=(a,b)=>a>0?(1-b/a)*100:null;
 const base=m.manualHours*m.hourlyRate+m.manualVendor,now=m.systemHours*m.hourlyRate+m.systemVendor+m.running;
 return {hoursSaved:m.manualHours-m.systemHours,drawingReduction:pct(m.manualHours,m.systemHours),daysReduction:pct(m.manualDays,m.systemDays),vendorReduction:pct(m.manualVendor,m.systemVendor),netSaving:base-now,breakEven:base>now?Math.ceil(m.investment/(base-now)):null}
}
