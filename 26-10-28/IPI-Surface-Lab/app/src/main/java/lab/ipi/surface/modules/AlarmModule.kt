package lab.ipi.surface.modules

import android.content.Intent
import android.provider.AlarmClock

class AlarmModule {
    fun alarm(f: Map<String, String>): Intent {
        val hour = f.orEmpty("hour").toInt(); val minute = f.orEmpty("minute").toInt()
        require(hour in 0..23 && minute in 0..59) { "Hour 0..23; minute 0..59" }
        return Intent(AlarmClock.ACTION_SET_ALARM).putExtra(AlarmClock.EXTRA_HOUR, hour).putExtra(AlarmClock.EXTRA_MINUTES, minute)
            .putExtra(AlarmClock.EXTRA_MESSAGE, f.orEmpty("label")).putExtra(AlarmClock.EXTRA_SKIP_UI, false)
    }
    fun timer(f: Map<String, String>): Intent {
        val seconds = f.orEmpty("seconds").toInt(); require(seconds in 1..86400) { "Timer range: 1..86400 seconds" }
        return Intent(AlarmClock.ACTION_SET_TIMER).putExtra(AlarmClock.EXTRA_LENGTH, seconds)
            .putExtra(AlarmClock.EXTRA_MESSAGE, f.orEmpty("label")).putExtra(AlarmClock.EXTRA_SKIP_UI, false)
    }
    fun show() = Intent(AlarmClock.ACTION_SHOW_ALARMS)
}
