import { PageHeader } from '../components/ui/index.js'
import CsvUpload from '../components/CsvUpload.jsx'
import SurrogateAccuracy from '../components/SurrogateAccuracy.jsx'
import ForecastChart from '../components/ForecastChart.jsx'

export default function DataPage() {
  return (
    <>
      <PageHeader title="Data & models" description="Bring your own network, and check how well the forecasting and risk models perform." />
      <div className="grid gap-6 xl:grid-cols-2">
        <div className="space-y-6">
          <CsvUpload />
          <SurrogateAccuracy />
        </div>
        <ForecastChart />
      </div>
    </>
  )
}
